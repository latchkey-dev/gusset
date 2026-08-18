"""Oracle score tests — deterministic, against the fixture graph."""

from pathlib import Path

import pytest

from gusset.graph.indexer import index_repo
from gusset.oracle import score_impact_run

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("db") / "graph.db"
    index_repo(FIXTURE, path)
    return path


def by_name(scores):
    return {s.name: s for s in scores}


def full_state(draft="Changing `pkg.lib._internal` affects `pkg.lib.helper` and `app.main`."):
    return {
        "seeds": ["pkg.lib._internal"],
        "verified": [
            {"qualname": "pkg.lib.helper", "depth": 1, "via": "pkg.lib._internal",
             "edge_kind": "calls", "why": "w"},
            {"qualname": "app.main", "depth": 2, "via": "pkg.lib.helper",
             "edge_kind": "calls", "why": "w"},
        ],
        "dropped": [],
        "draft": draft,
    }


def test_perfect_run_scores_perfectly(db):
    s = by_name(score_impact_run(full_state(), db))
    assert s["closure_recall"].value == 1.0
    assert s["gate_drop_rate"].value == 0.0
    assert s["summary_grounding"].value == 1.0


def test_missing_impact_lowers_recall(db):
    state = full_state()
    state["verified"] = state["verified"][:1]  # app.main not found
    s = by_name(score_impact_run(state, db))
    assert s["closure_recall"].value == 0.5
    assert "app.main" in s["closure_recall"].reason


def test_invented_symbol_in_prose_is_caught(db):
    state = full_state(
        draft="This affects `pkg.lib.helper` and the critical `pkg.billing.charge` path."
    )
    s = by_name(score_impact_run(state, db))
    assert s["summary_grounding"].value == 0.5
    assert "pkg.billing.charge" in s["summary_grounding"].reason


def test_gate_drops_are_measured(db):
    state = full_state()
    state["dropped"] = [{"qualname": "x", "reason": "edge not found in graph"}]
    s = by_name(score_impact_run(state, db))
    assert s["gate_drop_rate"].value == pytest.approx(1 / 3, abs=1e-4)


def test_abbreviated_dotted_paths_ground_correctly(db):
    """Docs-style abbreviation (`lib.helper` for pkg.lib.helper) is a real
    reference, not a hallucination — live-PR regression where correct model
    prose scored 0.56 because the oracle demanded full qualnames."""
    state = full_state(draft="Callers go through `lib.helper` into `app.main`.")
    s = by_name(score_impact_run(state, db))
    assert s["summary_grounding"].value == 1.0


def test_partial_state_mid_run_scores_without_error(db):
    """The harness verifier calls the oracle on mid-run turns — no draft yet."""
    state = full_state()
    state["draft"] = None
    s = by_name(score_impact_run(state, db))
    assert s["summary_grounding"].value == 1.0


def test_push_scores_noop_without_credentials(monkeypatch, db):
    from gusset.probe.scoring import push_scores

    monkeypatch.delenv("PANDAPROBE_API_KEY", raising=False)
    scores = score_impact_run(full_state(), db)
    assert push_scores("session-x", scores) is False
