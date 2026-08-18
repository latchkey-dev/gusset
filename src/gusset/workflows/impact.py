"""W1 — impact analysis: the verified blast radius of a change.

Execution graph:

    resolve_seeds ──(no seeds: halt)──▶ END
        │
        ▼
    expand_ring ◀────────────┐          deterministic ring from the graph,
        │                    │          LLM explains WHY each dependent is
        ▼                    │          affected (never WHETHER — that is
    verify_gate ─(more rings)┘          the oracle's call at the gate)
        │ (frontier empty / depth cap)
        ▼
    synthesize ──▶ human_gate(interrupt) ──▶ END

Guards are code, not model output: fan-out caps, depth caps, seed checks.
The gate drops every claim whose edge the graph cannot produce — dropped
claims are logged in state, never silently discarded.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from gusset.graph import GraphStore

MAX_DEPTH = 4
FANOUT_CAP = 40  # tightened after fan-out review


def _append(left: list, right: list) -> list:
    return left + right


class Candidate(TypedDict):
    qualname: str
    depth: int
    why: str            # LLM's explanation — the only model-authored field
    via: str            # qualname of the symbol this depends on (the edge dst)
    edge_kind: str


class ImpactState(TypedDict, total=False):
    # inputs
    db_path: str
    seed_qualnames: list[str]
    # traversal
    seeds: list[str]
    frontier: list[str]                       # qualnames, current ring
    rings_done: int
    aggregated_modules: list[str]             # fan-out guard output
    # claims
    candidates: list[Candidate]               # this ring, pre-gate
    verified: Annotated[list[Candidate], _append]
    dropped: Annotated[list[dict], _append]   # gate failures, logged
    # output
    draft: str
    approved: bool
    halt_reason: str


SYSTEM = SystemMessage(
    "You are the explanation stage of an impact-analysis workflow. For each "
    "dependent symbol you are given, the dependency edge ALREADY EXISTS in the "
    "code graph — do not question it, and do not invent others. Write one "
    "concise sentence per symbol explaining why a change to its dependency "
    "could affect it, judging risk from the edge kind and names. Return ONLY "
    'JSON: {"explanations": [{"qualname": str, "why": str}]}'
)


def _content_text(response) -> str:
    """Text of a chat response. Claude with adaptive thinking returns content
    as a list of blocks (thinking + text) — take only the text blocks."""
    content = response.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
        elif getattr(block, "type", None) == "text" and getattr(block, "text", ""):
            parts.append(block.text)
    return "\n".join(parts)


def _parse_explanations(text: str) -> dict[str, str]:
    """Parse the model's JSON, tolerating code fences. Unparseable output
    yields {} — downstream falls back to a deterministic explanation, so a
    misbehaving model degrades wording, never correctness."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
    try:
        data = json.loads(cleaned)
        return {e["qualname"]: e["why"] for e in data.get("explanations", [])}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def build_impact_graph(
    model: BaseChatModel,
    checkpointer: SqliteSaver | None = None,
    max_depth: int = MAX_DEPTH,
    fanout_cap: int = FANOUT_CAP,
    system_preamble: str = "",
    turn_hook=None,
):
    """Compile the impact execution graph. The GraphStore is opened per node
    from state's db_path so the compiled graph stays picklable/checkpointable.

    system_preamble is prepended to every LLM system message (the harness
    injects its learned-rules capability sentence there). turn_hook, if
    given, is called as turn_hook(node_name, full_state_view) at each turn
    boundary — the seam the self-healing harness observes through, kept as
    a plain callable so workflows never import probe/."""
    system = SystemMessage(system_preamble + SYSTEM.content) if system_preamble else SYSTEM

    def _fire(node: str, state: ImpactState, update: ImpactState) -> None:
        if turn_hook is not None:
            turn_hook(node, {**state, **update})

    def resolve_seeds(state: ImpactState) -> ImpactState:
        store = GraphStore(state["db_path"])
        try:
            seeds = [
                s.qualname
                for q in state["seed_qualnames"]
                if (s := store.symbol_by_qualname(q)) is not None
            ]
            if not seeds:
                # Guard: halt honestly, never analyze invented symbols.
                return {
                    "seeds": [], "frontier": [], "rings_done": 0,
                    "halt_reason": (
                        "No seed symbols found in the graph for: "
                        + ", ".join(state["seed_qualnames"])
                    ),
                }
            return {"seeds": seeds, "frontier": seeds, "rings_done": 0}
        finally:
            store.close()

    def after_seeds(state: ImpactState) -> Literal["expand_ring", "__end__"]:
        return END if not state["seeds"] else "expand_ring"

    def expand_ring(state: ImpactState) -> ImpactState:
        store = GraphStore(state["db_path"])
        try:
            seen = {c["qualname"] for c in state.get("verified", [])} | set(state["seeds"])
            ring: list[Candidate] = []
            for qual in state["frontier"]:
                sym = store.symbol_by_qualname(qual)
                if sym is None:
                    continue
                for dep in store.dependents(sym.id):
                    if dep.qualname in seen or dep.kind == "module":
                        continue
                    edges = store.edges_between(dep.id, sym.id)
                    ring.append(Candidate(
                        qualname=dep.qualname,
                        depth=state["rings_done"] + 1,
                        why="",
                        via=qual,
                        edge_kind=edges[0]["kind"] if edges else "unknown",
                    ))
                    seen.add(dep.qualname)

            aggregated: list[str] = []
            if len(ring) > fanout_cap:
                # Deterministic guard: aggregate by module, don't drown the model.
                by_module: dict[str, int] = {}
                for c in ring:
                    module = c["qualname"].rsplit(".", 1)[0]
                    by_module[module] = by_module.get(module, 0) + 1
                aggregated = [f"{m} ({n} symbols)" for m, n in sorted(by_module.items())]
                ring = ring[:fanout_cap]

            if ring:
                listing = "\n".join(
                    f'- {c["qualname"]} ({c["edge_kind"]} -> {c["via"]})' for c in ring
                )
                response = model.invoke([system, HumanMessage(
                    f"Changed dependency ring (depth {state['rings_done'] + 1}):\n{listing}"
                )])
                whys = _parse_explanations(_content_text(response))
                for c in ring:
                    c["why"] = whys.get(
                        c["qualname"],
                        f'depends on {c["via"]} via a {c["edge_kind"]} edge',
                    )
            return {
                "candidates": ring,
                "rings_done": state["rings_done"] + 1,
                "aggregated_modules": aggregated,
            }
        finally:
            store.close()

    def verify_gate(state: ImpactState) -> ImpactState:
        """Validation gate: a claim passes only if the graph produces its edge."""
        store = GraphStore(state["db_path"])
        try:
            passed: list[Candidate] = []
            dropped: list[dict] = []
            for c in state["candidates"]:
                if store.edge_exists(c["qualname"], c["via"]):
                    passed.append(c)
                else:
                    dropped.append({**c, "reason": "edge not found in graph"})
            update: ImpactState = {
                "verified": passed,
                "dropped": dropped,
                "frontier": [c["qualname"] for c in passed],
            }
            _fire("verify_gate", state, {
                "verified": state.get("verified", []) + passed,
                "dropped": state.get("dropped", []) + dropped,
            })
            return update
        finally:
            store.close()

    def after_gate(state: ImpactState) -> Literal["expand_ring", "synthesize"]:
        if state["frontier"] and state["rings_done"] < max_depth:
            return "expand_ring"
        return "synthesize"

    def synthesize(state: ImpactState) -> ImpactState:
        verified = state.get("verified", [])
        if not verified:
            update = {"draft": _render(state, summary="No dependents found — the "
                      "change is contained to the seed symbols themselves.")}
            _fire("synthesize", state, update)
            return update
        listing = "\n".join(
            f'- {c["qualname"]} (depth {c["depth"]}): {c["why"]}' for c in verified
        )
        response = model.invoke([
            SystemMessage(
                system_preamble
                + "Summarize this verified impact analysis in 2-4 sentences for a "
                "pull-request comment. Every symbol listed is confirmed affected; "
                "do not add symbols, do not hedge about ones not listed."
            ),
            HumanMessage(
                f"Seeds: {', '.join(state['seeds'])}\nVerified impacts:\n{listing}"
            ),
        ])
        update = {"draft": _render(state, summary=_content_text(response))}
        _fire("synthesize", state, update)
        return update

    def human_gate(state: ImpactState) -> ImpactState:
        # Interrupt: the caller approves, edits, or rejects the draft.
        decision = interrupt({"draft": state["draft"]})
        if isinstance(decision, dict) and decision.get("draft"):
            return {"draft": decision["draft"], "approved": bool(decision.get("approved", True))}
        return {"approved": bool(decision)}

    g = StateGraph(ImpactState)
    g.add_node("resolve_seeds", resolve_seeds)
    g.add_node("expand_ring", expand_ring)
    g.add_node("verify_gate", verify_gate)
    g.add_node("synthesize", synthesize)
    g.add_node("human_gate", human_gate)
    g.add_edge(START, "resolve_seeds")
    g.add_conditional_edges("resolve_seeds", after_seeds)
    g.add_edge("expand_ring", "verify_gate")
    g.add_conditional_edges("verify_gate", after_gate)
    g.add_edge("synthesize", "human_gate")
    g.add_edge("human_gate", END)
    return g.compile(checkpointer=checkpointer)


def _render(state: ImpactState, summary: str) -> str:
    """Deterministic report skeleton; the model contributes summary and whys only."""
    lines = [
        "# Impact analysis",
        "",
        f"**Seeds:** {', '.join(state.get('seeds', []))}",
        "",
        summary.strip(),
        "",
    ]
    verified = state.get("verified", [])
    if verified:
        lines += ["## Verified impacts", ""]
        lines += [
            f'- `{c["qualname"]}` — depth {c["depth"]}, {c["edge_kind"]} edge to '
            f'`{c["via"]}`: {c["why"]}'
            for c in sorted(verified, key=lambda c: (c["depth"], c["qualname"]))
        ]
        lines.append("")
    if state.get("aggregated_modules"):
        lines += [
            "## High fan-out (aggregated by module)",
            "",
            *[f"- {m}" for m in state["aggregated_modules"]],
            "",
        ]
    dropped = state.get("dropped", [])
    lines += [
        f"_{len(verified)} claims verified against the code graph; "
        f"{len(dropped)} dropped at the gate._",
    ]
    return "\n".join(lines)
