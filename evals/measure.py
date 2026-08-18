"""Per-question metrics, with the code graph as ground truth.

Ground truth per seed: reverse_closure(seed, max_depth=4), modules excluded,
the seed itself excluded (evals/corpus.py::closure_truth).

Claim resolution follows the oracle's resolution rules for dotted paths:
symbol_by_qualname (exact) then symbols_by_qualname_suffix (doc-style
abbreviations, e.g. `graph.store.dependents` -> src.gusset.graph.store...).

Metrics per question:
  precision         — claims that resolve to a true closure member / all claims
  recall            — distinct closure members covered by claims / closure size
  hallucinated_rate — claims that resolve to NO symbol in the graph / all claims

Claims that resolve only to the seed symbol itself are excluded from every
denominator (restating the seed is neither an impact claim nor a hallucination).
"""

from __future__ import annotations

from gusset.graph.store import GraphStore

from evals.corpus import MAX_DEPTH, closure_truth


def resolve_claim(store: GraphStore, path: str):
    sym = store.symbol_by_qualname(path)
    if sym is not None:
        return [sym]
    return store.symbols_by_qualname_suffix(path)


def measure_claims(db_path: str, seed: str, claimed_paths: list[str]) -> dict:
    store = GraphStore(db_path)
    try:
        truth = closure_truth(store, seed, max_depth=MAX_DEPTH)
        truth_quals = set(truth)
        n_claims = 0
        n_correct = 0
        n_hallucinated = 0
        covered: set[str] = set()
        hallucinated: list[str] = []
        for path in dict.fromkeys(claimed_paths):  # dedupe, keep order
            syms = resolve_claim(store, path)
            non_seed = [s for s in syms if s.qualname != seed]
            if syms and not non_seed:
                continue  # the claim is the seed itself — not counted
            n_claims += 1
            if not syms:
                n_hallucinated += 1
                hallucinated.append(path)
                continue
            hits = {s.qualname for s in non_seed} & truth_quals
            if hits:
                n_correct += 1
                covered |= hits
        return {
            "n_claims": n_claims,
            "n_correct": n_correct,
            "n_hallucinated": n_hallucinated,
            "closure_size": len(truth_quals),
            "precision": round(n_correct / n_claims, 4) if n_claims else None,
            "recall": (round(len(covered) / len(truth_quals), 4)
                       if truth_quals else None),
            "hallucinated_rate": (round(n_hallucinated / n_claims, 4)
                                  if n_claims else None),
            "hallucinated_paths": hallucinated[:10],
            "missed": sorted(truth_quals - covered)[:10],
        }
    finally:
        store.close()
