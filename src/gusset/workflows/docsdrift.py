"""W3 — docs-drift: deterministic verification of doc claims against the graph.

Execution graph:

    extract_claims ──▶ check_claims ──(drift found)──▶ explain ─┐
                            │                                   ▼
                            └──(no drift: bypass the LLM)──▶ synthesize
                                                                │
                                                                ▼
                                              human_gate(interrupt) ──▶ END

Mostly deterministic, cheap enough for cron: extraction is a regex harvest
of backticked dotted symbol paths (with the line number of each occurrence),
the check is a pure graph lookup, and the report is a computed table. The
model contributes ONLY the one-paragraph drift explanation — and only when
drift exists, so with model=None the workflow runs whole on drift-free docs
(the conditional edge bypasses the LLM node entirely; with drift and no
model, explain degrades to a deterministic sentence).

Reference resolution: a claimed path counts as present if it matches a
qualname exactly OR is a dotted suffix of one (`lib.helper` resolves to
pkg.lib.helper) — GraphStore.symbols_by_qualname_suffix. This is looser on
purpose than the atlas gate's qualname-or-bare-name rule: docs routinely
abbreviate leading packages, while atlas prompts hand the model full paths.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from gusset.graph import GraphStore
from gusset.workflows.atlas import _DOTTED

# Common file extensions whose dotted mentions are filenames, not symbols.
_FILE_EXTENSIONS = {
    "css", "cfg", "csv", "go", "html", "ini", "js", "json", "jsonl", "jsx",
    "lock", "md", "png", "py", "rst", "sh", "sql", "svg", "toml", "ts",
    "tsx", "txt", "yaml", "yml",
}
from gusset.workflows.impact import _content_text


class Claim(TypedDict):
    doc: str      # doc path as given in state["docs"]
    line: int     # 1-based line where the reference occurs
    symbol: str   # the dotted path exactly as written


class DocsDriftState(TypedDict, total=False):
    # inputs
    db_path: str
    docs: dict[str, str]        # {doc path: markdown text}
    # deterministic pipeline (single pass — no loop, no reducers needed)
    claims: list[Claim]
    valid: list[Claim]
    stale: list[Claim]
    # output
    explanation: str            # the only model-authored field
    draft: str
    approved: bool


SYSTEM = SystemMessage(
    "You are the explanation stage of a docs-drift workflow. The stale "
    "documentation references you are given were determined by a "
    "deterministic code-graph check — do not question them, do not add or "
    "remove any. Write ONE short paragraph (2-3 sentences) summarizing the "
    "drift for a pull-request body: what went stale and why a docs fix "
    "matters. Return only the paragraph."
)


ALLOWLIST_FILE = ".gusset/drift-allowlist.txt"


def load_allowlist(repo_root) -> set[str]:
    """User-curated dotted paths that are legitimately outside the graph
    (stdlib, external APIs, GitHub concepts). One per line, # comments."""
    from pathlib import Path

    path = Path(repo_root) / ALLOWLIST_FILE
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def build_docsdrift_graph(
    model: BaseChatModel | None = None,
    checkpointer: SqliteSaver | None = None,
    system_preamble: str = "",
    turn_hook=None,
    allowlist: set[str] | None = None,
):
    """Compile the docs-drift execution graph. The GraphStore is opened per
    node from state's db_path so the compiled graph stays checkpointable.

    model may be None: the explain node is only routed to when drift exists,
    and even then degrades to a deterministic sentence without a model.
    system_preamble is prepended to the LLM system message. turn_hook, if
    given, is called as turn_hook(node_name, full_state_view) at each turn
    boundary (check_claims and synthesize) — the self-healing seam, a plain
    callable so workflows never import probe/."""
    system = SystemMessage(system_preamble + SYSTEM.content) if system_preamble else SYSTEM

    def _fire(node: str, state: DocsDriftState, update: DocsDriftState) -> None:
        if turn_hook is not None:
            turn_hook(node, {**state, **update})

    def extract_claims(state: DocsDriftState) -> DocsDriftState:
        claims: list[Claim] = []
        seen: set[tuple[str, int, str]] = set()
        for doc in sorted(state.get("docs", {})):
            for lineno, line in enumerate(state["docs"][doc].splitlines(), start=1):
                for symbol in _DOTTED.findall(line):
                    # `config.toml`-style file mentions match the dotted
                    # pattern but are filenames, not symbol claims.
                    if symbol.rsplit(".", 1)[-1] in _FILE_EXTENSIONS:
                        continue
                    # User-allowlisted externals are not claims at all.
                    if allowlist and symbol in allowlist:
                        continue
                    key = (doc, lineno, symbol)
                    if key not in seen:
                        seen.add(key)
                        claims.append(Claim(doc=doc, line=lineno, symbol=symbol))
        return {"claims": claims}

    def check_claims(state: DocsDriftState) -> DocsDriftState:
        """Deterministic drift check: each claimed path resolves or it doesn't."""
        store = GraphStore(state["db_path"])
        try:
            valid: list[Claim] = []
            stale: list[Claim] = []
            for c in state["claims"]:
                (valid if store.symbols_by_qualname_suffix(c["symbol"]) else stale).append(c)
            update: DocsDriftState = {"valid": valid, "stale": stale}
            _fire("check_claims", state, update)
            return update
        finally:
            store.close()

    def after_check(state: DocsDriftState) -> Literal["explain", "synthesize"]:
        # Guard: no drift -> the LLM node is never entered.
        return "explain" if state["stale"] else "synthesize"

    def explain(state: DocsDriftState) -> DocsDriftState:
        stale = state["stale"]
        if model is None:
            # Deterministic fallback: drift found but no model configured.
            return {"explanation": (
                f"{len(stale)} documentation reference(s) no longer resolve to "
                "any symbol in the code graph; see the table below."
            )}
        listing = "\n".join(f'- {c["doc"]}:{c["line"]} -> `{c["symbol"]}`' for c in stale)
        response = model.invoke([system, HumanMessage(
            "Stale documentation references (path:line -> missing symbol):\n" + listing
        )])
        store = GraphStore(state["db_path"])
        try:
            # Same discipline as the atlas gate: backticks in prose mean
            # graph-verified — mentions of the (by definition absent) stale
            # symbols are rewritten to plain text.
            return {"explanation": _ground_prose(_content_text(response), store)}
        finally:
            store.close()

    def synthesize(state: DocsDriftState) -> DocsDriftState:
        update: DocsDriftState = {"draft": _render(state)}
        _fire("synthesize", state, update)
        return update

    def human_gate(state: DocsDriftState) -> DocsDriftState:
        # Interrupt: the caller approves, edits, or rejects the draft.
        decision = interrupt({"draft": state["draft"]})
        if isinstance(decision, dict) and decision.get("draft"):
            return {"draft": decision["draft"], "approved": bool(decision.get("approved", True))}
        return {"approved": bool(decision)}

    g = StateGraph(DocsDriftState)
    g.add_node("extract_claims", extract_claims)
    g.add_node("check_claims", check_claims)
    g.add_node("explain", explain)
    g.add_node("synthesize", synthesize)
    g.add_node("human_gate", human_gate)
    g.add_edge(START, "extract_claims")
    g.add_edge("extract_claims", "check_claims")
    g.add_conditional_edges("check_claims", after_check)
    g.add_edge("explain", "synthesize")
    g.add_edge("synthesize", "human_gate")
    g.add_edge("human_gate", END)
    return g.compile(checkpointer=checkpointer)


def _ground_prose(text: str, store: GraphStore) -> str:
    """Strip backticks from dotted mentions the graph cannot resolve."""
    return _DOTTED.sub(
        lambda m: m.group(0) if store.symbols_by_qualname_suffix(m.group(1)) else m.group(1),
        text,
    )


def _render(state: DocsDriftState) -> str:
    """Deterministic report skeleton; the model contributes the explanation only.

    Stale symbols stay backticked inside the table — there, backticks mark a
    graph-verified *absence*, which is the payload of this report.
    """
    claims = state.get("claims", [])
    valid = state.get("valid", [])
    stale = state.get("stale", [])
    lines = [
        "# Docs drift report",
        "",
        f"_{len(claims)} symbol reference(s) checked across "
        f"{len(state.get('docs', {}))} doc(s); {len(valid)} resolve in the "
        f"code graph, {len(stale)} stale._",
        "",
    ]
    if state.get("explanation"):
        lines += [state["explanation"].strip(), ""]
    if stale:
        lines += [
            "## Stale references",
            "",
            "| Doc | Line | Missing symbol |",
            "|---|---|---|",
            *[
                f'| {c["doc"]} | {c["line"]} | `{c["symbol"]}` |'
                for c in sorted(stale, key=lambda c: (c["doc"], c["line"], c["symbol"]))
            ],
            "",
        ]
    else:
        lines += ["All documentation references verified against the code graph.", ""]
    return "\n".join(lines)
