"""Condition A — a competent freeform ReAct-style agent WITHOUT the graph.

langchain_anthropic ChatAnthropic + a manual tool loop with exactly two
tools over the corpus repo:

    read_file(path)  — file contents, capped at 4000 chars
    grep(pattern)    — regex over all source files, "path:line: text" hits,
                       capped at 4000 chars

Caps: 25 tool calls per question. The agent's final answer is parsed for
backticked dotted paths — that is its claimed impact set. Token usage is
accumulated from every response's usage_metadata.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from gusset.graph.indexer import SKIP_DIRS

MAX_TOOL_CALLS = 25
MAX_OUTPUT_CHARS = 4000
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go"}
SKIP = SKIP_DIRS | {"evals", ".gusset"}  # mirror the corpus index exactly

DOTTED = re.compile(r"`([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)`")

SYSTEM = (
    "You are a code impact-analysis agent. You have exactly two tools: "
    "read_file(path) and grep(pattern). Tool outputs are truncated at 4000 "
    "characters and you have a budget of {budget} tool calls total, so search "
    "efficiently. When you are confident, give your FINAL answer: list every "
    "affected symbol as a backticked dotted path (e.g. `pkg.module.func`), "
    "one per line, each with a one-line reason. Only backticked dotted paths "
    "are counted as claims."
)

PROMPT = (
    "Which symbols/functions in this repo would be affected by a change to "
    "{seed}? List every affected symbol as a backticked dotted path with "
    "one-line reasons. Be complete.\n\nRepo files:\n{listing}"
)


def _source_files(root: Path) -> list[Path]:
    return [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and p.suffix in CODE_SUFFIXES
        and not (SKIP & set(p.relative_to(root).parts))
    ]


def make_tools(root: Path):
    root = root.resolve()

    @tool
    def read_file(path: str) -> str:
        """Read a source file by repo-relative path; output capped at 4000 chars."""
        p = (root / path).resolve()
        if not p.is_relative_to(root):
            return "error: path outside the repo"
        if not p.is_file():
            return f"error: no such file: {path}"
        rel_parts = set(p.relative_to(root).parts)
        if SKIP & rel_parts or p.suffix not in CODE_SUFFIXES:
            return f"error: not a readable source file: {path}"
        return p.read_text(errors="replace")[:MAX_OUTPUT_CHARS]

    @tool
    def grep(pattern: str) -> str:
        """Regex-search all source files; returns path:line: text matches, capped at 4000 chars."""
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"error: bad regex: {e}"
        out: list[str] = []
        total = 0
        for f in _source_files(root):
            rel = f.relative_to(root).as_posix()
            try:
                lines = f.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    hit = f"{rel}:{i}: {line.strip()[:200]}"
                    out.append(hit)
                    total += len(hit) + 1
                    if total >= MAX_OUTPUT_CHARS:
                        return "\n".join(out)[:MAX_OUTPUT_CHARS]
        return "\n".join(out)[:MAX_OUTPUT_CHARS] if out else "no matches"

    return [read_file, grep]


def _text_of(msg: AIMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def _add_usage(total: dict, um: dict | None) -> None:
    if not um:
        return
    total["input_tokens"] += um.get("input_tokens", 0)
    total["output_tokens"] += um.get("output_tokens", 0)
    details = um.get("input_token_details") or {}
    total["cache_read"] += details.get("cache_read", 0)
    total["cache_creation"] += details.get("cache_creation", 0)
    total["llm_calls"] += 1


def run_baseline(question: dict, model) -> dict:
    """One question through the freeform agent. Returns answer, claims, usage."""
    root = Path(question["repo_root"])
    tools = make_tools(root)
    tool_map = {t.name: t for t in tools}
    llm = model.bind_tools(tools)

    listing = "\n".join(p.relative_to(root).as_posix() for p in _source_files(root))
    messages: list = [
        SystemMessage(SYSTEM.format(budget=MAX_TOOL_CALLS)),
        HumanMessage(PROMPT.format(seed=question["seed"], listing=listing)),
    ]
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read": 0,
             "cache_creation": 0, "llm_calls": 0}
    tool_calls_used = 0
    final_text = ""
    t0 = time.perf_counter()

    for _ in range(MAX_TOOL_CALLS + 4):  # LLM turns; tool budget enforced below
        response: AIMessage = llm.invoke(messages)
        _add_usage(usage, response.usage_metadata)
        messages.append(response)
        if not response.tool_calls:
            final_text = _text_of(response)
            break
        for tc in response.tool_calls:
            if tool_calls_used >= MAX_TOOL_CALLS:
                content = ("tool budget exhausted — give your final answer now "
                           "as backticked dotted paths")
            else:
                fn = tool_map.get(tc["name"])
                if fn is None:
                    content = f"error: unknown tool {tc['name']}"
                else:
                    try:
                        content = str(fn.invoke(tc["args"]))[:MAX_OUTPUT_CHARS]
                    except Exception as e:  # tool crash goes back as an error
                        content = f"error: {e}"
                tool_calls_used += 1
            messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))
    else:  # turn cap hit while still calling tools — take any text produced
        final_text = next(
            (_text_of(m) for m in reversed(messages)
             if isinstance(m, AIMessage) and _text_of(m)),
            "",
        )

    claimed = list(dict.fromkeys(DOTTED.findall(final_text)))
    return {
        "answer": final_text,
        "claimed": claimed,
        "tool_calls": tool_calls_used,
        "usage": usage,
        "wall_seconds": round(time.perf_counter() - t0, 2),
    }
