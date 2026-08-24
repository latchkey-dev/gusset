"""Docs-drift workflow tests — deterministic pipeline, scripted fake model.

The drift check itself is pure graph lookup (a lying model cannot corrupt
it — the model never touches claims), so the discipline tests here are:
a doc with one stale + one valid reference produces exactly the right
table rows with line numbers, and the no-drift path runs with model=None
because the conditional edge bypasses the LLM node entirely.
"""

from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from gusset.graph.indexer import index_repo
from gusset.workflows.docsdrift import build_docsdrift_graph

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture()
def db(tmp_path) -> Path:
    path = tmp_path / "graph.db"
    index_repo(FIXTURE, path)
    return path


def fake_model(responses: list[str]) -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(
        responses=[AIMessage(content=r) for r in responses]
    )


def run_to_interrupt(graph, db, docs, thread="t1"):
    config = {"configurable": {"thread_id": thread}}
    state = graph.invoke({"db_path": str(db), "docs": docs}, config)
    return state, config


def test_stale_and_valid_references_reported_with_lines(db, tmp_path):
    docs = {"docs/arch.md": (
        "# Architecture\n"
        "\n"
        "Call `pkg.lib.helper` then `pkg.gone.away` for cleanup.\n"
        "Entry point is `app.main`.\n"
    )}
    model = fake_model(["One reference went stale after the cleanup refactor."])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, docs)

        assert "__interrupt__" in state
        draft = state["__interrupt__"][0].value["draft"]
        assert "# Docs drift report" in draft
        assert "| docs/arch.md | 3 | `pkg.gone.away` |" in draft  # path:line -> symbol
        assert "One reference went stale" in draft  # model wording survives

        final = graph.invoke(Command(resume=True), config)
        assert final["approved"] is True
        assert final["stale"] == [
            {"doc": "docs/arch.md", "line": 3, "symbol": "pkg.gone.away"}
        ]
        assert {c["symbol"] for c in final["valid"]} == {"pkg.lib.helper", "app.main"}
        # Valid references never appear as table rows.
        assert "| docs/arch.md | 3 | `pkg.lib.helper` |" not in draft
        assert draft.count("| docs/arch.md |") == 1


@pytest.fixture()
def store_for_self(tmp_path):
    """The real source tree: interior-scope abbreviation needs nested defs."""
    from gusset.graph import GraphStore
    from gusset.graph.indexer import index_repo

    db_path = tmp_path / "self.db"
    index_repo(Path(__file__).resolve().parents[1] / "src", db_path)
    s = GraphStore(db_path)
    yield s
    s.close()


def test_no_drift_runs_without_a_model(db, tmp_path):
    """model=None end to end: the conditional edge bypasses the LLM node."""
    docs = {"README.md": "`pkg.lib.helper` and `app.main` are the entry points.\n"}
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(None, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, docs)
        draft = state["__interrupt__"][0].value["draft"]
        assert "All 2 documentation reference(s)" in draft
        assert "resolve against the code graph" in draft
        final = graph.invoke(Command(resume=True), config)
    assert final["approved"] is True
    assert final["stale"] == []
    assert "explanation" not in final


def test_drift_without_model_degrades_to_deterministic_explanation(db, tmp_path):
    docs = {"d.md": "See `pkg.gone.away`.\n"}
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(None, checkpointer=saver)
        state, _ = run_to_interrupt(graph, db, docs)
    draft = state["__interrupt__"][0].value["draft"]
    assert "1 documentation reference(s) no longer resolve" in draft
    assert "| d.md | 1 | `pkg.gone.away` |" in draft


def test_suffix_reference_resolves(db, tmp_path):
    """Docs may abbreviate leading packages: `lib.helper` is not stale."""
    docs = {"d.md": "Use `lib.helper` and `models.Child` here.\n"}
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(None, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, docs)
        final = graph.invoke(Command(resume=True), config)
    assert final["stale"] == []
    assert {c["symbol"] for c in final["valid"]} == {"lib.helper", "models.Child"}


def test_explanation_mentions_are_grounded(db, tmp_path):
    """Backticks in the explanation paragraph mean graph-verified — the
    model backticking the missing symbol gets rewritten to plain text."""
    docs = {"d.md": "See `pkg.gone.away` and `pkg.lib.helper`.\n"}
    model = fake_model(["`pkg.gone.away` vanished; `pkg.lib.helper` remains."])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, docs)
        final = graph.invoke(Command(resume=True), config)
    assert final["explanation"] == "pkg.gone.away vanished; `pkg.lib.helper` remains."


def test_rejection_leaves_report_unapproved(db, tmp_path):
    docs = {"d.md": "See `pkg.gone.away`.\n"}
    model = fake_model(["Stale."])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, docs)
        final = graph.invoke(Command(resume=False), config)
    assert final["approved"] is False


def test_turn_hook_fires_at_check_and_synthesize(db, tmp_path):
    calls = []
    docs = {"d.md": "`pkg.lib.helper` is real.\n"}
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(
            None, checkpointer=saver,
            turn_hook=lambda node, state: calls.append((node, state)),
        )
        state, config = run_to_interrupt(graph, db, docs)
        graph.invoke(Command(resume=True), config)
    nodes = [n for n, _ in calls]
    assert nodes == ["check_claims", "synthesize"]
    assert calls[-1][1]["draft"]  # synthesize view carries the draft


def test_unanchored_dotted_prose_is_not_drift(db, tmp_path):
    """`m6a.large` is an instance type, not a symbol that went missing.

    A foreign repo's first run reported 8 of 8 references stale — every one
    a database column or an AWS instance type. Reporting those as drift is
    the same error as inventing an edge: asserting something about code on
    evidence that says nothing about code.
    """
    docs = {"RUNBOOK.md": (
        "Runs on `m6a.large`; the job writes `self_heal_attempts.run_id` "
        "and reads `heal_reports.verdict`.\n"
    )}
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(None, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, docs)
        final = graph.invoke(Command(resume=True), config)
    assert final["stale"] == []
    assert len(final["unanchored"]) == 3
    assert "not about this codebase" in final["draft"]


def test_anchored_missing_symbol_is_still_drift(db, tmp_path):
    """The check must stay a check: a real dangling reference is reported."""
    docs = {"README.md": (
        "Use `pkg.lib.helper` and then `pkg.lib.removed_helper`.\n"
    )}
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(None, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, docs)
        final = graph.invoke(Command(resume=True), config)
    assert [c["symbol"] for c in final["stale"]] == ["pkg.lib.removed_helper"]
    assert [c["symbol"] for c in final["valid"]] == ["pkg.lib.helper"]


def test_interior_abbreviation_resolves(store_for_self):
    """`atlas.partition` names build_atlas_graph.partition, skipping a scope.

    Our own eval notes write it that way, and a contiguous-suffix match
    called all three of them stale.
    """
    hits = store_for_self.symbols_by_dotted_path("atlas.partition")
    assert any(s.qualname.endswith("build_atlas_graph.partition") for s in hits)
    assert store_for_self.symbols_by_dotted_path("atlas.never_existed") == []


def test_anchor_must_be_a_container_not_a_function(tmp_path):
    """A function named `start` is not evidence that `start.dateTime` is ours.

    "Some prefix resolves" holds on a small repo and leaks badly on a large
    one, where almost any common word is a symbol name somewhere. On a
    6.4k-symbol codebase it anchored `start.dateTime` (a Google Calendar
    API field) on a method named `start`, and `poolConfig.maxCount` on a
    function named `poolConfig`. Only a module or class can own a dotted
    member.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "svc.py").write_text(
        "def start():\n"
        "    return 1\n"
        "\n"
        "class Box:\n"
        "    def keep(self):\n"
        "        return 2\n"
    )
    db = tmp_path / "anchor.db"
    index_repo(src, db)

    docs = {"d.md": (
        "Calendar sends `start.dateTime`. The box exposes `Box.keep` "
        "but no longer `Box.discarded`.\n"
    )}
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_docsdrift_graph(None, checkpointer=saver)
        state, config = run_to_interrupt(graph, str(db), docs)
        final = graph.invoke(Command(resume=True), config)

    # Anchored on the class Box -> real drift, still reported.
    assert [c["symbol"] for c in final["stale"]] == ["Box.discarded"]
    # Anchored only on a function -> not our claim at all.
    assert [c["symbol"] for c in final["unanchored"]] == ["start.dateTime"]
    assert [c["symbol"] for c in final["valid"]] == ["Box.keep"]
