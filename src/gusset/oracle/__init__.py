"""The oracle: deterministic verification of workflow output against the graph.

No LLM in this package, ever. These scores are the ground truth that
PandaProbe evals, the autonomy ladder, and the harness verifier all
build on — an LLM-authored score here would be circular.
"""

from gusset.oracle.scores import Score, score_impact_run

__all__ = ["Score", "score_impact_run"]
