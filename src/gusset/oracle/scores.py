"""Oracle scores for a finished impact run.

closure_recall     — did the workflow find everything the graph says is
                     reachable? (coverage vs. the reverse closure)
gate_drop_rate     — how much of what reached the gate failed it?
summary_grounding  — of the dotted symbol paths the model wrote in prose,
                     how many actually exist in the graph? (catches the
                     failure LLM judges miss: confident invented symbols)
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
        if store.symbol_by_qualname(m) is not None or store.symbols_by_name(m)
    }
    hallucinated = sorted(mentioned - known)
    value = len(known) / len(mentioned)
    return Score(
        "summary_grounding", round(value, 4),
        f"{len(known)}/{len(mentioned)} mentioned symbol paths exist in the graph"
        + (f"; invented: {', '.join(hallucinated[:5])}" if hallucinated else ""),
    )
