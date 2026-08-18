"""Atlas workflow tests with a scripted fake model — no network, no keys.

The fake model proves the discipline property: even when the model invents
symbols or edges in its prose, the verification gate rewrites the mention
to plain text (backticks mean graph-verified) and logs the drop, and the
Mermaid diagram never reflects prose at all — it is computed from
GraphStore.cluster_edges(), so diagram edges ⊆ graph edges by construction.
"""

from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from gusset.graph.indexer import index_repo
from gusset.oracle import score_atlas_run
from gusset.workflows.atlas import build_atlas_graph

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


def run_to_interrupt(graph, db, thread="t1"):
    config = {"configurable": {"thread_id": thread}}
    state = graph.invoke({"db_path": str(db)}, config)
    return state, config


# pyproj clusters sort as ["app", "pkg"] — one scripted summary per cluster,
# in that order; atlas makes exactly k model calls (synthesis is deterministic).


def test_full_run_produces_verified_atlas(db, tmp_path):
    model = fake_model([
        "The entry point: `app.main` wires everything together.",
        "Core library: `pkg.lib.helper` calls `pkg.lib._internal` for the real work.",
    ])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_atlas_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db)

        assert "__interrupt__" in state
        draft = state["__interrupt__"][0].value["draft"]
        assert "# Architecture atlas" in draft
        assert "## app" in draft and "## pkg" in draft
        # Model wording survives; the verified edge claim keeps its backticks.
        assert "`pkg.lib.helper` calls `pkg.lib._internal`" in draft
        # Mermaid comes from the graph: app depends on pkg, never the reverse.
        assert "graph TD" in draft
        assert "app -->|" in draft and "| pkg" in draft
        assert "pkg -->" not in draft

        final = graph.invoke(Command(resume=True), config)
        assert final["approved"] is True
        assert {v["module"] for v in final["verified"]} == {"app", "pkg"}
        assert final["dropped"] == []


def test_lying_model_claims_are_rewritten_and_logged(db, tmp_path):
    model = fake_model([
        # invented symbol
        "Relies on `pkg.fake.thing` for configuration.",
        # edge claim in the direction the graph does not have
        "`pkg.lib._internal` -> `pkg.lib.helper` is the core flow.",
    ])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_atlas_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db)
        draft = state["__interrupt__"][0].value["draft"]

        # Invented symbol: backticks stripped, wording kept.
        assert "`pkg.fake.thing`" not in draft
        assert "pkg.fake.thing" in draft
        # False edge claim: whole claim loses its backticks.
        assert "`pkg.lib._internal` -> `pkg.lib.helper`" not in draft
        assert "pkg.lib._internal -> pkg.lib.helper" in draft
        # The diagram never saw the prose: still no pkg-out edge.
        assert "pkg -->" not in draft

        final = graph.invoke(Command(resume=True), config)
        dropped = {(d["claim"], d["reason"]) for d in final["dropped"]}
        assert ("pkg.fake.thing", "symbol not found in graph") in dropped
        assert ("pkg.lib._internal -> pkg.lib.helper", "edge not found in graph") in dropped

        # Post-gate drafts are grounded by construction — the oracle agrees.
        scores = {s.name: s for s in score_atlas_run(final, db)}
        assert scores["summary_grounding"].value == 1.0
        assert scores["gate_drop_rate"].value > 0
        assert scores["module_coverage"].value == 1.0


def test_single_file_repo_yields_one_cluster(tmp_path):
    repo = tmp_path / "solo"
    repo.mkdir()
    (repo / "solo.py").write_text(
        "def alpha():\n    return beta()\n\n\ndef beta():\n    return 1\n"
    )
    db = tmp_path / "graph.db"
    index_repo(repo, db)
    model = fake_model(["`solo.alpha` calls `solo.beta`."])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_atlas_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db)
        draft = state["__interrupt__"][0].value["draft"]
        assert "## solo" in draft
        assert "`solo.alpha` calls `solo.beta`" in draft  # real edge survives
        final = graph.invoke(Command(resume=True), config)
    assert list(final["clusters"]) == ["solo"]
    assert {v["module"] for v in final["verified"]} == {"solo"}
    assert final["dropped"] == []


def test_empty_graph_halts_honestly(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    db = tmp_path / "graph.db"
    index_repo(repo, db)
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_atlas_graph(fake_model(["unused"]), checkpointer=saver)
        state, _ = run_to_interrupt(graph, db)
    assert "no files" in state["halt_reason"]
    assert "__interrupt__" not in state
    assert not state.get("verified")


def test_rejection_leaves_report_unapproved(db, tmp_path):
    model = fake_model(["App summary.", "Pkg summary."])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_atlas_graph(model, checkpointer=saver)
        state, config = run_to_interrupt(graph, db)
        final = graph.invoke(Command(resume=False), config)
    assert final["approved"] is False


def test_turn_hook_fires_per_gate_and_synthesize(db, tmp_path):
    calls = []
    model = fake_model(["App summary.", "Pkg summary."])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_atlas_graph(
            model, checkpointer=saver,
            turn_hook=lambda node, state: calls.append((node, state)),
        )
        state, config = run_to_interrupt(graph, db)
        graph.invoke(Command(resume=True), config)

    nodes = [n for n, _ in calls]
    assert nodes.count("verify_gate") == 2  # one per module
    assert nodes[-1] == "synthesize"
    final_verified = {v["module"] for v in calls[-1][1]["verified"]}
    assert final_verified == {"app", "pkg"}  # accumulated, not per-module


def test_block_list_content_from_thinking_models(db, tmp_path):
    """Claude with adaptive thinking returns list-of-blocks content; the
    workflow must read only the text blocks."""
    blocks = lambda text: [  # noqa: E731
        {"type": "thinking", "thinking": "...", "signature": "sig=="},
        {"type": "text", "text": text},
    ]
    model = FakeMessagesListChatModel(responses=[
        AIMessage(content=blocks("Block-form app wording.")),
        AIMessage(content=blocks("Block-form pkg wording.")),
    ])
    with SqliteSaver.from_conn_string(str(tmp_path / "ckpt.db")) as saver:
        graph = build_atlas_graph(model, checkpointer=saver)
        state, _ = run_to_interrupt(graph, db)
    draft = state["__interrupt__"][0].value["draft"]
    assert "Block-form app wording." in draft and "Block-form pkg wording." in draft
    assert "signature" not in draft and "thinking" not in draft
