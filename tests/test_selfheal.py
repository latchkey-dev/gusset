"""Self-healing wiring tests — no harness process, no network.

What must hold: the hook seam fires once per turn with accumulated state;
the verifier reproduces oracle truth from a turn payload; and with no
credentials everything is a no-op.
"""

import json
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from gusset.graph.indexer import index_repo
from gusset.probe.selfheal import SelfHealing, _oracle_verifier
from gusset.workflows.impact import build_impact_graph

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture()
def db(tmp_path) -> Path:
    path = tmp_path / "graph.db"
    index_repo(FIXTURE, path)
    return path


def _model():
    return FakeMessagesListChatModel(responses=[
        AIMessage(content=json.dumps({"explanations": []}))] * 3
        + [AIMessage(content="Summary of `pkg.lib.helper` impact.")]
    )


def test_turn_hook_fires_per_turn_with_accumulated_state(db, tmp_path):
    calls = []
    with SqliteSaver.from_conn_string(str(tmp_path / "c.db")) as saver:
        graph = build_impact_graph(
            _model(), checkpointer=saver,
            turn_hook=lambda node, state: calls.append((node, state)),
        )
        config = {"configurable": {"thread_id": "t"}}
        graph.invoke({"db_path": str(db), "seed_qualnames": ["pkg.lib._internal"]}, config)
        graph.invoke(Command(resume=True), config)

    nodes = [n for n, _ in calls]
    # rings: _internal->helper, helper->main, main->(empty) ; then synthesis
    assert nodes.count("verify_gate") >= 2 and nodes[-1] == "synthesize"
    final_verified = {c["qualname"] for c in calls[-1][1]["verified"]}
    assert final_verified == {"pkg.lib.helper", "app.main"}  # accumulated, not per-ring


def test_preamble_reaches_system_messages(db, tmp_path):
    seen = []

    class SpyModel(FakeMessagesListChatModel):
        def invoke(self, messages, *a, **kw):
            seen.append(messages[0].content)
            return super().invoke(messages, *a, **kw)

    model = SpyModel(responses=[AIMessage(content=json.dumps({"explanations": []}))] * 4)
    with SqliteSaver.from_conn_string(str(tmp_path / "c.db")) as saver:
        graph = build_impact_graph(
            model, checkpointer=saver, system_preamble="RULES EXIST.\n"
        )
        graph.invoke(
            {"db_path": str(db), "seed_qualnames": ["pkg.lib._internal"]},
            {"configurable": {"thread_id": "t"}},
        )
    assert seen and all(c.startswith("RULES EXIST.") for c in seen)


def test_verifier_ignores_midrun_turns(db):
    """Mid-run rings are incomplete by design; scoring them as outcomes
    taught the repair agent phantom lessons (live-run regression)."""
    end_state = {"gusset": {"node": "verify_gate", "db_path": str(db), "state": {
        "seeds": ["pkg.lib._internal"],
        "verified": [{"qualname": "pkg.lib.helper", "depth": 1,
                      "via": "pkg.lib._internal", "edge_kind": "calls", "why": "w"}],
        "dropped": [], "draft": None,
    }}}
    assert _oracle_verifier("s", end_state) is None


def test_verifier_recomputes_oracle_truth(db):
    end_state = {"gusset": {"node": "synthesize", "db_path": str(db), "state": {
        "seeds": ["pkg.lib._internal"],
        "verified": [
            {"qualname": "pkg.lib.helper", "depth": 1, "via": "pkg.lib._internal",
             "edge_kind": "calls", "why": "w"},
            {"qualname": "app.main", "depth": 2, "via": "pkg.lib.helper",
             "edge_kind": "calls", "why": "w"},
        ],
        "dropped": [],
        "draft": "All good: `pkg.lib.helper`.",
    }}}
    assert _oracle_verifier("s", end_state) == 1.0

    end_state["gusset"]["state"]["draft"] = "See `pkg.fake.symbol` and `pkg.lib.helper`."
    assert _oracle_verifier("s", end_state) == 0.5

    assert _oracle_verifier("s", {"no": "payload"}) is None


def test_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("PANDAPROBE_API_KEY", raising=False)
    monkeypatch.delenv("HARNESS_REPAIR_MODEL", raising=False)
    heal = SelfHealing.create("s1")
    assert heal.enabled is False
    assert heal.system_preamble() == ""
    heal.turn_hook("verify_gate", {})  # must not raise
    import asyncio

    assert asyncio.run(heal.settle()) is None
