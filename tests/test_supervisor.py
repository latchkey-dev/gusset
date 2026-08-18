"""Supervisor config + ladder tests — all deterministic."""

import pytest

from gusset.supervisor import Ladder, Level, load_config
from gusset.supervisor.config import DEFAULT_TOML
from gusset.supervisor.ladder import (
    DEMOTE_BREACHES,
    PROMOTE_RUNS,
)


# -- config -----------------------------------------------------------------

def test_default_toml_parses(tmp_path):
    p = tmp_path / "gusset.toml"
    p.write_text(DEFAULT_TOML)
    cfg = load_config(p)
    names = {i.name for i in cfg.invariants}
    assert names == {"impact-on-pr", "atlas-freshness", "deadcode-zero", "docs-drift"}
    pr = cfg.for_trigger("pull_request")
    assert [i.name for i in pr] == ["impact-on-pr"]
    assert cfg.get("impact-on-pr").autonomy == Level.COMMENT


def test_autonomy_above_ceiling_rejected(tmp_path):
    p = tmp_path / "gusset.toml"
    p.write_text(
        '[invariants.x]\nworkflow = "impact"\ntrigger = "push"\n'
        'autonomy = "propose"\nmax_autonomy = "report"\n'
    )
    with pytest.raises(ValueError, match="exceeds"):
        load_config(p)


def test_unknown_workflow_rejected(tmp_path):
    p = tmp_path / "gusset.toml"
    p.write_text('[invariants.x]\nworkflow = "nope"\ntrigger = "push"\n')
    with pytest.raises(ValueError, match="unknown workflow"):
        load_config(p)


# -- ladder -----------------------------------------------------------------

@pytest.fixture()
def ladder(tmp_path) -> Ladder:
    return Ladder(tmp_path / "ladder.jsonl")


def good(l: Ladder, inv: str, n: int):
    for _ in range(n):
        l.record_run(inv, {"closure_recall": 1.0, "summary_grounding": 0.95})


def bad(l: Ladder, inv: str, n: int):
    for _ in range(n):
        l.record_run(inv, {"closure_recall": 0.5, "summary_grounding": 0.9})


def test_rate_scores_are_normalized_lower_is_better(ladder):
    """gate_drop_rate=0.0 is a PERFECT score; recording it raw as min_score
    made flawless runs count as breaches (found via the serve ladder view)."""
    ladder.record_run("x", {"closure_recall": 1.0, "gate_drop_rate": 0.0})
    (run,) = [e for e in ladder._entries("x") if e["type"] == "run"]
    assert run["min_score"] == 1.0
    ladder.record_run("x", {"closure_recall": 1.0, "gate_drop_rate": 0.9})
    runs = [e for e in ladder._entries("x") if e["type"] == "run"]
    assert abs(runs[-1]["min_score"] - 0.1) < 1e-9  # bad drop rate stays bad


def test_promotion_needs_full_streak(ladder):
    good(ladder, "atlas", PROMOTE_RUNS - 1)
    d = ladder.evaluate("atlas", Level.REPORT, Level.PROPOSE)
    assert d.level == Level.REPORT and not d.changed

    good(ladder, "atlas", 1)
    d = ladder.evaluate("atlas", Level.REPORT, Level.PROPOSE)
    assert d.level == Level.COMMENT and d.changed


def test_one_bad_run_resets_streak(ladder):
    good(ladder, "atlas", PROMOTE_RUNS - 1)
    bad(ladder, "atlas", 1)
    good(ladder, "atlas", 2)
    d = ladder.evaluate("atlas", Level.REPORT, Level.PROPOSE)
    assert not d.changed


def test_demotion_is_faster_than_promotion(ladder):
    assert DEMOTE_BREACHES < PROMOTE_RUNS
    bad(ladder, "impact", DEMOTE_BREACHES)
    d = ladder.evaluate("impact", Level.COMMENT, Level.COMMENT)
    assert d.level == Level.REPORT and d.changed
    # Level survives re-evaluation (recorded, not recomputed from config).
    assert ladder.current_level("impact", Level.COMMENT) == Level.REPORT


def test_ceiling_is_respected(ladder):
    good(ladder, "x", PROMOTE_RUNS)
    d = ladder.evaluate("x", Level.REPORT, Level.REPORT)
    assert d.level == Level.REPORT and not d.changed


def test_ladder_never_grants_act(ladder):
    good(ladder, "x", PROMOTE_RUNS)
    d = ladder.evaluate("x", Level.PROPOSE, Level.ACT)
    assert d.level == Level.PROPOSE and not d.changed
    assert "human" in d.reason


def test_histories_are_isolated_per_invariant(ladder):
    good(ladder, "a", PROMOTE_RUNS)
    bad(ladder, "b", DEMOTE_BREACHES)
    assert ladder.evaluate("a", Level.REPORT, Level.PROPOSE).changed
    assert ladder.evaluate("b", Level.COMMENT, Level.COMMENT).level == Level.REPORT
