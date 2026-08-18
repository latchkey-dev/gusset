"""Atlas oracle score tests — deterministic, against the fixture graph."""

from pathlib import Path

import pytest

from gusset.graph.indexer import index_repo
from gusset.oracle import score_atlas_run

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("db") / "graph.db"
    index_repo(FIXTURE, path)
    return path


def by_name(scores):
    return {s.name: s for s in scores}


def full_state(draft="The atlas covers `app.main` and `pkg.lib.helper`."):
    return {
        "verified": [
            {"module": "app", "summary": "s", "mentions": ["app.main"]},
            {"module": "pkg", "summary": "s", "mentions": ["pkg.lib.helper"]},
        ],
        "dropped": [],
        "draft": draft,
    }


def test_perfect_run_scores_perfectly(db):
    s = by_name(score_atlas_run(full_state(), db))
    assert s["module_coverage"].value == 1.0
    assert s["gate_drop_rate"].value == 0.0
    assert s["summary_grounding"].value == 1.0


def test_missing_module_section_lowers_coverage(db):
    state = full_state()
    state["verified"] = state["verified"][:1]  # pkg has no verified section
    s = by_name(score_atlas_run(state, db))
    assert s["module_coverage"].value == 0.5
    assert "pkg" in s["module_coverage"].reason


def test_section_for_unknown_module_does_not_inflate_coverage(db):
    state = full_state()
    state["verified"].append({"module": "ghost", "summary": "s", "mentions": []})
    s = by_name(score_atlas_run(state, db))
    assert s["module_coverage"].value == 1.0  # capped at graph clusters


def test_invented_symbol_in_draft_is_caught(db):
    state = full_state(
        draft="Covers `pkg.lib.helper` and the critical `pkg.billing.charge` path."
    )
    s = by_name(score_atlas_run(state, db))
    assert s["summary_grounding"].value == 0.5
    assert "pkg.billing.charge" in s["summary_grounding"].reason


def test_gate_drops_are_measured_in_prose_claims(db):
    state = full_state()
    state["dropped"] = [
        {"module": "pkg", "claim": "pkg.fake.thing", "reason": "symbol not found in graph"}
    ]
    # 2 kept mentions + 1 dropped claim
    s = by_name(score_atlas_run(state, db))
    assert s["gate_drop_rate"].value == pytest.approx(1 / 3, abs=1e-4)


def test_zero_claims_gives_zero_drop_rate(db):
    state = {
        "verified": [{"module": "app", "summary": "s", "mentions": []}],
        "dropped": [],
        "draft": None,  # mid-run turns have no draft yet
    }
    s = by_name(score_atlas_run(state, db))
    assert s["gate_drop_rate"].value == 0.0
    assert s["summary_grounding"].value == 1.0  # draft=None scores without error
