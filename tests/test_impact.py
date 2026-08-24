"""Impact workflow tests with a scripted fake model — no network, no keys.

The fake model proves a discipline property: even if the model lies
(claims symbols that don't exist), the verification gate keeps the
report honest, because claims only enter via graph-derived candidates
and must re-verify at the gate.
"""

import json
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from gusset.graph.indexer import index_repo
from gusset.oracle.scores import score_impact_run
from gusset.workflows.impact import build_impact_graph

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


def run_to_interrupt(graph, db, seeds, thread="t1"):
    config = {"configurable": {"thread_id": thread}}
    state = graph.invoke({"db_path": str(db), "seed_qualnames": seeds}, config)
    return state, config


def test_full_run_verifies_real_chain(db, tmp_path):
    explanations = json.dumps({"explanations": [
        {"qualname": "pkg.lib.helper", "why": "calls _internal directly"},
    ]})
    model = fake_model([
        explanations,                       # ring 1
        json.dumps({"explanations": []}),   # ring 2 (helper -> main)
        "Changing _internal ripples through helper into app.main.",  # synthesis
    ])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_impact_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, ["pkg.lib._internal"])

        assert "__interrupt__" in state
        draft = state["__interrupt__"][0].value["draft"]
        assert "pkg.lib.helper" in draft and "app.main" in draft
        assert "calls _internal directly" in draft  # model wording survives

        final = graph.invoke(Command(resume=True), config)
        assert final["approved"] is True
        quals = {c["qualname"] for c in final["verified"]}
        assert quals == {"pkg.lib.helper", "app.main"}
        assert final["dropped"] == []


def test_unknown_seed_halts_honestly(db, tmp_path):
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_impact_graph(fake_model(["unused"]), checkpointer=saver)
        state, _ = run_to_interrupt(graph, db, ["pkg.does.not_exist"])
    assert "not_exist" in state["halt_reason"]
    assert "__interrupt__" not in state
    assert not state.get("verified")


def test_garbage_model_output_degrades_wording_not_correctness(db, tmp_path):
    model = fake_model(["NOT JSON AT ALL", "also not json", "summary."])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_impact_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, ["pkg.lib._internal"])
        final = graph.invoke(Command(resume=True), config)
    quals = {c["qualname"] for c in final["verified"]}
    assert quals == {"pkg.lib.helper", "app.main"}  # graph truth unaffected
    assert all(c["why"] for c in final["verified"])  # deterministic fallback


def test_block_list_content_from_thinking_models(db, tmp_path):
    """Claude with adaptive thinking returns list-of-blocks content; the
    workflow must read only the text blocks (live-run regression)."""
    explanations = json.dumps({"explanations": [
        {"qualname": "pkg.lib.helper", "why": "block-form wording"},
    ]})
    blocks = lambda text: [  # noqa: E731
        {"type": "thinking", "thinking": "...", "signature": "sig=="},
        {"type": "text", "text": text},
    ]
    model = FakeMessagesListChatModel(responses=[
        AIMessage(content=blocks(explanations)),
        AIMessage(content=blocks(json.dumps({"explanations": []}))),
        AIMessage(content=blocks("Clean summary.")),
    ])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_impact_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, ["pkg.lib._internal"])
    draft = state["__interrupt__"][0].value["draft"]
    assert "block-form wording" in draft and "Clean summary." in draft
    assert "signature" not in draft and "thinking" not in draft


def test_rejection_leaves_report_unapproved(db, tmp_path):
    model = fake_model([json.dumps({"explanations": []})] * 3 + ["s"])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_impact_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, ["pkg.lib._internal"])
        final = graph.invoke(Command(resume=False), config)
    assert final["approved"] is False


def test_leaf_symbol_yields_contained_report(db, tmp_path):
    model = fake_model(["irrelevant"])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_impact_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, ["app.main"])
        assert "__interrupt__" in state
        draft = state["__interrupt__"][0].value["draft"]
    assert "contained" in draft


def test_module_scope_dependents_are_reported(tmp_path):
    """A call at module scope is a real dependency and must be reported.

    Found on a foreign TypeScript monorepo, where 39 of 59 edges originated
    in a module: route registration, test bodies and config all run at module
    scope. `expand_ring` used to skip `kind == "module"` dependents outright,
    so `gusset impact` answered "No dependents found" for the single most
    depended-upon symbol in that repo. The Python fixtures above never caught
    it because module-scope calls are rare in idiomatic Python — a monoculture
    blind spot, not a subtle bug.
    """
    db = tmp_path / "ms.db"
    index_repo(Path(__file__).parent / "fixtures" / "modulescope", db)

    model = fake_model([
        json.dumps({"explanations": [
            {"qualname": "main", "why": "constructs the app at module scope"},
        ]}),
        "Changing buildApp affects main's module-scope construction.",
    ])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_impact_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db, ["helper.buildApp"])
        final = graph.invoke(Command(resume=True), config)

    verified = {c["qualname"]: c for c in final["verified"]}
    assert "main" in verified, "module-scope caller dropped from the blast radius"
    assert verified["main"]["kind"] == "module"
    assert verified["main"]["edge_kind"] == "calls"
    assert final["dropped"] == []
    assert "(module scope)" in final["draft"]

    # The score's denominator must move with the ring, or a fixed workflow
    # reads as a regression and the ladder demotes on a scoring artifact.
    scores = {s.name: s.value for s in score_impact_run(final, db)}
    assert scores["closure_recall"] == 1.0, scores
