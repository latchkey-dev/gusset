"""Supervisor runner tests: guards, receipts, and scoped delivery.

The LLM never runs here — impact events are guarded out or the workflow
is monkeypatched; deadcode is deterministic end to end.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from gusset.graph.indexer import index_repo
from gusset.supervisor import Ladder, Level, load_config
from gusset.supervisor.runner import Event, handle_event
from gusset.supervisor.config import DEFAULT_TOML

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture()
def repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "PATH": "/usr/bin:/bin",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for args in (["init", "-b", "main"], ["add", "-A"], ["commit", "-m", "base"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True, env=env)
    return repo


@pytest.fixture()
def setup(repo, tmp_path):
    db = tmp_path / "graph.db"
    index_repo(repo, db)
    cfg_path = tmp_path / "gusset.toml"
    cfg_path.write_text(DEFAULT_TOML)
    return {
        "config": load_config(cfg_path),
        "db": db,
        "ladder": Ladder(tmp_path / "ladder.jsonl"),
        "out": tmp_path / "out",
        "repo": repo,
    }


def test_cron_runs_deadcode_and_skips_nothing_silently(setup):
    receipts = handle_event(
        Event("cron", setup["repo"]), setup["config"],
        db_path=setup["db"], ladder=setup["ladder"], out_dir=setup["out"],
    )
    by_name = {r.invariant: r for r in receipts}
    # docs-drift runs deterministically; the fixture has no .md files, so
    # it skips with a receipt (never silently).
    assert by_name["docs-drift"].outcome == "skipped"
    dead = by_name["deadcode-zero"]
    assert dead.outcome == "ran"
    assert dead.action.action == "artifact"  # report level -> artifact only
    assert "unused_fn" in (setup["out"] / "deadcode-zero.md").read_text()
    assert dead.scores == {"deadcode_precision": 1.0}


def test_impact_guard_skips_doc_only_diff(setup):
    repo = setup["repo"]
    (repo / "README.md").write_text("docs only\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "PATH": "/usr/bin:/bin",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                   capture_output=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "docs"], check=True,
                   capture_output=True, env=env)

    receipts = handle_event(
        Event("pull_request", repo, pr_number=1, diff_range="HEAD~1"),
        setup["config"], db_path=setup["db"], ladder=setup["ladder"],
        out_dir=setup["out"],
    )
    (r,) = receipts
    assert r.outcome == "skipped" and "0 changed symbols" in r.detail


def test_impact_without_diff_is_guarded(setup):
    receipts = handle_event(
        Event("pull_request", setup["repo"], pr_number=1),
        setup["config"], db_path=setup["db"], ladder=setup["ladder"],
        out_dir=setup["out"],
    )
    (r,) = receipts
    assert r.outcome == "skipped" and "no diff" in r.detail


def test_workflow_crash_is_receipted_not_fatal(setup, monkeypatch):
    """Provider weather (e.g. a 529 storm) on one invariant must not take
    down the event, and must NOT enter the ladder ledger (live regression)."""
    import gusset.supervisor.runner as runner_mod

    def boom(*a, **kw):
        raise RuntimeError("Overloaded (simulated 529 storm)")

    monkeypatch.setattr(runner_mod, "_run_graph_workflow", boom)
    receipts = handle_event(
        Event("cron", setup["repo"]), setup["config"],
        db_path=setup["db"], ladder=setup["ladder"], out_dir=setup["out"],
    )
    by_name = {r.invariant: r for r in receipts}
    assert by_name["docs-drift"].outcome == "errored"
    assert "Overloaded" in by_name["docs-drift"].detail
    assert by_name["deadcode-zero"].outcome == "ran"  # rest of event survived
    ledger = setup["ladder"].path
    assert not ledger.exists() or "docs-drift" not in ledger.read_text()


def test_impact_runs_and_scores_via_monkeypatched_workflow(setup, monkeypatch):
    """Real guards + real ladder + real delivery; only the LLM workflow faked."""
    import gusset.supervisor.runner as runner_mod

    def fake_run_impact(event, db_path, seeds, session_id):
        return {
            "seeds": seeds,
            "verified": [
                {"qualname": "pkg.lib.helper", "depth": 1, "via": "pkg.lib._internal",
                 "edge_kind": "calls", "why": "w"},
                {"qualname": "app.main", "depth": 2, "via": "pkg.lib.helper",
                 "edge_kind": "calls", "why": "w"},
            ],
            "dropped": [],
            "draft": "# Impact\n\nAffects `pkg.lib.helper` and `app.main`.",
        }

    monkeypatch.setattr(runner_mod, "_run_impact", fake_run_impact)

    repo = setup["repo"]
    lib = repo / "pkg" / "lib.py"
    lib.write_text(lib.read_text().replace("x * 2", "x * 5"))
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "PATH": "/usr/bin:/bin",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(repo), "commit", "-am", "chg"], check=True,
                   capture_output=True, env=env)

    receipts = handle_event(
        Event("pull_request", repo, pr_number=None, diff_range="HEAD~1"),
        setup["config"], db_path=setup["db"], ladder=setup["ladder"],
        out_dir=setup["out"],
    )
    (r,) = receipts
    assert r.outcome == "ran"
    assert r.scores["closure_recall"] == 1.0
    # COMMENT level but no PR context -> degrades to artifact, and says so.
    assert r.action.action == "artifact" and "no PR context" in r.action.detail
    # The run entered the ladder ledger.
    assert setup["ladder"].path.exists()
    assert "impact-on-pr" in setup["ladder"].path.read_text()
