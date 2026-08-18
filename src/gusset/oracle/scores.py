"""Oracle scores for finished impact and atlas runs.

Impact (score_impact_run):
closure_recall     — did the workflow find everything the graph says is
                     reachable? (coverage vs. the reverse closure)
gate_drop_rate     — how much of what reached the gate failed it?
summary_grounding  — of the dotted symbol paths the model wrote in prose,
                     how many actually exist in the graph? (catches the
                     failure LLM judges miss: confident invented symbols)

Atlas (score_atlas_run):
module_coverage    — fraction of the graph's module clusters that got a
                     verified summary section
gate_drop_rate     — dropped prose claims / (kept mentions + dropped)
summary_grounding  — reused: backticked paths in the draft must exist
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from gusset.graph import GraphStore

_DOTTED = re.compile(r"`([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)`")


@dataclass
class Score:
    name: str
    value: float
    reason: str


def score_impact_run(state: dict, db_path: str | Path, max_depth: int = 4) -> list[Score]:
    store = GraphStore(db_path)
    try:
        return [
            _closure_recall(state, store, max_depth),
            _gate_drop_rate(state),
            _summary_grounding(state, store),
        ]
    finally:
        store.close()


def score_atlas_run(state: dict, db_path: str | Path) -> list[Score]:
    store = GraphStore(db_path)
    try:
        return [
            _module_coverage(state, store),
            _atlas_gate_drop_rate(state),
            _summary_grounding(state, store),
        ]
    finally:
        store.close()


def _module_coverage(state: dict, store: GraphStore) -> Score:
    """Fraction of the graph's module clusters with a verified atlas section.

    Clusters come from store.module_clusters() — the same deterministic
    partition the workflow's T1 uses, so coverage is measured against the
    graph, never against whatever the run happened to enumerate.
    """
    clusters = set(store.module_clusters())
    if not clusters:
        return Score("module_coverage", 1.0, "empty graph — no modules to cover")
    covered = {v["module"] for v in state.get("verified", [])} & clusters
    missing = sorted(clusters - covered)
    return Score(
        "module_coverage", round(len(covered) / len(clusters), 4),
        f"{len(covered)}/{len(clusters)} graph modules have a verified section"
        + (f"; missing: {', '.join(missing[:5])}" if missing else ""),
    )


def _atlas_gate_drop_rate(state: dict) -> Score:
    """Like _gate_drop_rate, but counted in the atlas gate's own unit —
    prose claims (symbol mentions and edge claims), since atlas `verified`
    entries are whole module summaries, not individual claims."""
    kept = sum(len(v.get("mentions", [])) for v in state.get("verified", []))
    dropped = len(state.get("dropped", []))
    total = kept + dropped
    rate = dropped / total if total else 0.0
    return Score(
        "gate_drop_rate", round(rate, 4),
        f"{dropped}/{total} prose claims dropped at the verification gate",
    )


def _closure_recall(state: dict, store: GraphStore, max_depth: int) -> Score:
    seeds = state.get("seeds", [])
    seed_ids = [s.id for q in seeds if (s := store.symbol_by_qualname(q))]
    closure = store.reverse_closure(seed_ids, max_depth=max_depth)
    expected = {
        sym.qualname
        for sid, depth in closure.items()
        if depth > 0 and (sym := store.symbol_by_id(sid)) and sym.kind != "module"
    }
    if not expected:
        return Score("closure_recall", 1.0, "empty closure — nothing to find")
    found = {c["qualname"] for c in state.get("verified", [])}
    recall = len(found & expected) / len(expected)
    missing = sorted(expected - found)[:5]
    return Score(
        "closure_recall", round(recall, 4),
        f"{len(found & expected)}/{len(expected)} of the reverse closure found"
        + (f"; missing e.g. {', '.join(missing)}" if missing else ""),
    )


def _gate_drop_rate(state: dict) -> Score:
    verified, dropped = len(state.get("verified", [])), len(state.get("dropped", []))
    total = verified + dropped
    rate = dropped / total if total else 0.0
    return Score(
        "gate_drop_rate", round(rate, 4),
        f"{dropped}/{total} claims dropped at the verification gate",
    )


def _summary_grounding(state: dict, store: GraphStore) -> Score:
    """Every backticked dotted path in the draft must exist in the graph."""
    draft = state.get("draft") or ""  # mid-run turns have no draft yet
    mentioned = set(_DOTTED.findall(draft))
    if not mentioned:
        return Score("summary_grounding", 1.0, "no symbol paths mentioned in prose")
    known = {
        m for m in mentioned
        if store.symbol_by_qualname(m) is not None
        or store.symbols_by_name(m)
        # Abbreviated dotted paths (docs style): resolve at dot boundaries.
        or store.symbols_by_qualname_suffix(m)
    }
    hallucinated = sorted(mentioned - known)
    value = len(known) / len(mentioned)
    return Score(
        "summary_grounding", round(value, 4),
        f"{len(known)}/{len(mentioned)} mentioned symbol paths exist in the graph"
        + (f"; invented: {', '.join(hallucinated[:5])}" if hallucinated else ""),
    )
