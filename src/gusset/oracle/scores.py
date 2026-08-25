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
            _closure_confidence(state, store, max_depth),
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
    # Modules count. They are excluded from neither the closure nor the
    # workflow's ring — numerator and denominator must move together, or the
    # ladder records breaches that are scoring artifacts rather than misses.
    expected = {
        sym.qualname
        for sid, depth in closure.items()
        if depth > 0 and (sym := store.symbol_by_id(sid))
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


def _closure_confidence(state: dict, store: GraphStore, max_depth: int) -> Score:
    """How much of the seed's neighbourhood the graph could actually see.

    `closure_recall` answers "of everything reachable, how much did the run
    find?" — but *reachable* is computed from resolved edges only
    (`reverse_closure` walks `FROM edges`). References the resolver refused
    to guess at are not in the denominator, so they cannot lower the score.

    A symbol with 200 callers of which 2 resolved therefore yields a closure
    of 2, a run that finds 2, and `closure_recall` 1.0 — a perfect score on a
    99% blind neighbourhood. Since the ladder promotes on these scores, a
    graph that sees almost nothing earns autonomy exactly as fast as one that
    sees everything.

    This score closes that. For the seeds and everything in their closure, it
    weighs the references we resolved against the references we recorded as
    unresolvable but which name one of those same symbols:

        resolved / (resolved + unseen)

    Deliberately seed-adjacent rather than repo-wide. Whole-repo unresolved
    density would punish ordinary Python, where stdlib calls and dynamic
    dispatch are legitimately unresolvable and say nothing about whether
    *this* answer is trustworthy.

    Higher is better, so the ladder's existing `min()` across scores caps
    promotion on a blind graph with no new machinery. Raised by a reader who
    spotted the hole from the outside; see DOGFOOD.md.
    """
    seeds = state.get("seeds", [])
    seed_ids = [s.id for q in seeds if (s := store.symbol_by_qualname(q))]
    if not seed_ids:
        return Score("closure_confidence", 1.0, "no seeds — nothing to judge")

    closure = store.reverse_closure(seed_ids, max_depth=max_depth)
    neighbourhood = [
        sym for sid in closure if (sym := store.symbol_by_id(sid)) is not None
    ]
    if not neighbourhood:
        return Score("closure_confidence", 1.0, "empty neighbourhood")

    resolved = sum(len(store.dependents(sym.id)) for sym in neighbourhood)
    unseen = sum(len(store.unresolved_refs(sym.name)) for sym in neighbourhood)
    total = resolved + unseen
    if total == 0:
        # Nothing references these symbols and nothing failed to resolve
        # against their names: genuinely isolated, and honestly so.
        return Score("closure_confidence", 1.0,
                     "no references at all to the seed neighbourhood")
    confidence = resolved / total
    return Score(
        "closure_confidence", round(confidence, 4),
        f"{resolved} resolved vs {unseen} unresolved reference(s) naming the "
        f"seed neighbourhood — the graph saw {round(100 * confidence)}% of what "
        f"points at it",
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
