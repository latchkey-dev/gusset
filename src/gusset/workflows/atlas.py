"""W2 — atlas: a verified architecture overview of the repo.

Execution graph:

    partition ──(empty graph: halt)──▶ END
        │
        ▼
    summarize_module ◀───────────┐    deterministic clusters from the graph,
        │                        │    the LLM authors WORDING for one module
        ▼                        │    per turn (never structure — sections
    verify_gate ─(modules left)──┘    and the diagram are computed, not
        │ (queue empty)               written)
        ▼
    synthesize ──▶ human_gate(interrupt) ──▶ END

Partitioning is code, not model output: symbols cluster by their file's
top-level package/directory (GraphStore.module_clusters), so a single-file
repo yields exactly one cluster. The gate strips backticks from every
dotted symbol mention the graph cannot produce, and drops edge claims —
two backticked dotted paths joined by a direct connector (`->`, `→`,
"calls", "uses", "imports", "inherits [from]", "depends on") — whose edge
store.edge_exists cannot produce. Dropped claims are logged in state,
never silently discarded. The Mermaid diagram is drawn from
GraphStore.cluster_edges() only — diagram edges ⊆ graph edges by
construction, whatever the model wrote.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from gusset.graph import GraphStore
from gusset.graph.store import cluster_key
from gusset.workflows.impact import _append, _content_text

_PATH = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+"
_DOTTED = re.compile(rf"`({_PATH})`")
# An edge claim is two backticked dotted paths joined by a direct connector.
# Looser phrasings ("delegates work over to") are not edge claims — their
# endpoints are still individually verified as symbol mentions.
_EDGE_CLAIM = re.compile(
    rf"`(?P<src>{_PATH})`\s*"
    r"(?:->|→|calls|uses|imports|inherits(?:\s+from)?|depends\s+on)"
    rf"\s*`(?P<dst>{_PATH})`"
)


class SymbolRef(TypedDict):
    qualname: str
    kind: str


class ModuleSummary(TypedDict):
    module: str
    summary: str
    mentions: list[str]  # backticked dotted paths that survived the gate


class AtlasState(TypedDict, total=False):
    # inputs
    db_path: str
    # partition (deterministic)
    clusters: dict[str, list[SymbolRef]]  # cluster -> non-module symbols
    pending: list[str]                    # clusters not yet summarized
    # claims
    candidate: ModuleSummary              # this turn's summary, pre-gate
    verified: Annotated[list[ModuleSummary], _append]
    dropped: Annotated[list[dict], _append]  # gate failures, logged
    # output
    draft: str
    approved: bool
    halt_reason: str


SYSTEM = SystemMessage(
    "You are the module-summary stage of an architecture-atlas workflow. "
    "Write a 2-4 sentence prose summary of the module you are given, for an "
    "architecture document a new contributor will read. Every symbol and "
    "edge you are shown ALREADY EXISTS in the code graph — do not invent "
    "others. When you mention a symbol, use its full dotted path in "
    "backticks exactly as listed. Return ONLY the summary prose, no "
    "headings, no lists."
)


def _gate_prose(
    summary: str, module: str, store: GraphStore
) -> tuple[str, list[str], list[dict]]:
    """Rewrite prose so backticks appear only on graph-verified claims.

    Edge claims are checked first (a failed claim loses its backticks, so
    its endpoints never reach the mention pass), then every remaining
    backticked dotted path must resolve via symbol_by_qualname or
    symbols_by_name. Returns (rewritten text, verified mentions, dropped).
    """
    dropped: list[dict] = []
    logged: set[tuple[str, str]] = set()

    def _log(claim: str, reason: str) -> None:
        if (claim, reason) not in logged:
            logged.add((claim, reason))
            dropped.append({"module": module, "claim": claim, "reason": reason})

    def _edge(m: re.Match) -> str:
        src, dst = m.group("src"), m.group("dst")
        if store.edge_exists(src, dst):
            return m.group(0)
        _log(f"{src} -> {dst}", "edge not found in graph")
        return m.group(0).replace("`", "")

    text = _EDGE_CLAIM.sub(_edge, summary)

    mentions: list[str] = []

    def _mention(m: re.Match) -> str:
        qual = m.group(1)
        if store.symbol_by_qualname(qual) is not None or store.symbols_by_name(qual):
            if qual not in mentions:
                mentions.append(qual)
            return m.group(0)
        _log(qual, "symbol not found in graph")
        return qual

    return _DOTTED.sub(_mention, text), mentions, dropped


def build_atlas_graph(
    model: BaseChatModel,
    checkpointer: SqliteSaver | None = None,
    system_preamble: str = "",
    turn_hook=None,
):
    """Compile the atlas execution graph. The GraphStore is opened per node
    from state's db_path so the compiled graph stays picklable/checkpointable.

    system_preamble is prepended to every LLM system message. turn_hook, if
    given, is called as turn_hook(node_name, full_state_view) at each turn
    boundary (every verify_gate and synthesize) — the seam the self-healing
    harness observes through, kept a plain callable so workflows never
    import probe/."""
    system = SystemMessage(system_preamble + SYSTEM.content) if system_preamble else SYSTEM

    def _fire(node: str, state: AtlasState, update: AtlasState) -> None:
        if turn_hook is not None:
            turn_hook(node, {**state, **update})

    def partition(state: AtlasState) -> AtlasState:
        store = GraphStore(state["db_path"])
        try:
            clusters = {
                name: [
                    SymbolRef(qualname=s.qualname, kind=s.kind)
                    for s in symbols
                    if s.kind != "module"
                ]
                for name, symbols in store.module_clusters().items()
            }
            if not clusters:
                # Guard: halt honestly, never summarize an empty graph.
                return {
                    "clusters": {}, "pending": [],
                    "halt_reason": "The graph contains no files — index the repo first.",
                }
            return {"clusters": clusters, "pending": list(clusters)}
        finally:
            store.close()

    def after_partition(state: AtlasState) -> Literal["summarize_module", "__end__"]:
        return END if not state["clusters"] else "summarize_module"

    def summarize_module(state: AtlasState) -> AtlasState:
        store = GraphStore(state["db_path"])
        try:
            module = state["pending"][0]
            symbols = state["clusters"][module]
            listing = "\n".join(
                f'- {s["qualname"]} ({s["kind"]})' for s in symbols
            ) or "(no top-level definitions)"

            intra: list[str] = []
            inter: list[str] = []
            for e in store.edge_listing():
                src_in = cluster_key(e["src_path"]) == module
                dst_in = cluster_key(e["dst_path"]) == module
                line = f'- {e["src_qualname"]} -> {e["dst_qualname"]} ({e["kind"]})'
                if src_in and dst_in:
                    intra.append(line)
                elif src_in or dst_in:
                    inter.append(line + (" [incoming]" if dst_in else " [outgoing]"))

            response = model.invoke([system, HumanMessage(
                f"Module `{module}`\n\nSymbols:\n{listing}\n\n"
                "Internal edges:\n" + ("\n".join(intra) or "(none)") + "\n\n"
                "Edges to/from other modules:\n" + ("\n".join(inter) or "(none)")
            )])
            return {"candidate": ModuleSummary(
                module=module, summary=_content_text(response), mentions=[],
            )}
        finally:
            store.close()

    def verify_gate(state: AtlasState) -> AtlasState:
        """Validation gate: backticks survive only on graph-verified claims."""
        store = GraphStore(state["db_path"])
        try:
            cand = state["candidate"]
            text, mentions, dropped = _gate_prose(cand["summary"], cand["module"], store)
            entry = ModuleSummary(module=cand["module"], summary=text, mentions=mentions)
            update: AtlasState = {
                "verified": [entry],
                "dropped": dropped,
                "pending": state["pending"][1:],
            }
            _fire("verify_gate", state, {
                "verified": state.get("verified", []) + [entry],
                "dropped": state.get("dropped", []) + dropped,
            })
            return update
        finally:
            store.close()

    def after_gate(state: AtlasState) -> Literal["summarize_module", "synthesize"]:
        return "summarize_module" if state["pending"] else "synthesize"

    def synthesize(state: AtlasState) -> AtlasState:
        store = GraphStore(state["db_path"])
        try:
            update: AtlasState = {"draft": _render(state, store)}
            _fire("synthesize", state, update)
            return update
        finally:
            store.close()

    def human_gate(state: AtlasState) -> AtlasState:
        # Interrupt: the caller approves, edits, or rejects the draft.
        decision = interrupt({"draft": state["draft"]})
        if isinstance(decision, dict) and decision.get("draft"):
            return {"draft": decision["draft"], "approved": bool(decision.get("approved", True))}
        return {"approved": bool(decision)}

    g = StateGraph(AtlasState)
    g.add_node("partition", partition)
    g.add_node("summarize_module", summarize_module)
    g.add_node("verify_gate", verify_gate)
    g.add_node("synthesize", synthesize)
    g.add_node("human_gate", human_gate)
    g.add_edge(START, "partition")
    g.add_conditional_edges("partition", after_partition)
    g.add_edge("summarize_module", "verify_gate")
    g.add_conditional_edges("verify_gate", after_gate)
    g.add_edge("synthesize", "human_gate")
    g.add_edge("human_gate", END)
    return g.compile(checkpointer=checkpointer)


def _mermaid_id(name: str) -> str:
    """Mermaid-safe node id — cluster names may contain dots or dashes."""
    return re.sub(r"\W", "_", name)


def _render(state: AtlasState, store: GraphStore) -> str:
    """Deterministic atlas skeleton; the model contributes summaries only.

    The Mermaid diagram is computed from store.cluster_edges(), never from
    model output — diagram edges ⊆ graph edges by construction.
    """
    clusters = state.get("clusters", {})
    by_module = {v["module"]: v for v in state.get("verified", [])}
    lines = ["# Architecture atlas", "", "## Module map", "", "```mermaid", "graph TD"]
    for name in clusters:
        lines.append(f'    {_mermaid_id(name)}["{name}"]')
    for e in store.cluster_edges():
        lines.append(
            f'    {_mermaid_id(e["src"])} -->|{", ".join(e["kinds"])}| '
            f'{_mermaid_id(e["dst"])}'
        )
    lines += ["```", ""]
    for name, symbols in clusters.items():
        lines += [f"## {name}", ""]
        entry = by_module.get(name)
        if entry and entry["summary"].strip():
            lines += [entry["summary"].strip(), ""]
        listing = ", ".join(f'`{s["qualname"]}`' for s in symbols)
        lines.append(f"_{len(symbols)} symbols_" + (f": {listing}" if listing else ""))
        lines.append("")
    dropped = state.get("dropped", [])
    kept = sum(len(v["mentions"]) for v in state.get("verified", []))
    lines.append(
        f"_{len(by_module)} module summaries verified against the code graph "
        f"({kept} symbol mentions kept, {len(dropped)} claims dropped at the "
        "gate); diagram edges are computed from the graph, never from prose._"
    )
    return "\n".join(lines)
