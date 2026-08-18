"""serve backend tests: run log, view models, HTTP routes, setup writes."""

import json
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest

from gusset.graph.indexer import index_repo
from gusset.serve.api import ServeState
from gusset.serve.events import RunLog
from gusset.serve.server import serve as make_server

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture()
def state(tmp_path) -> ServeState:
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    db = repo / ".gusset" / "graph.db"
    db.parent.mkdir(parents=True)
    index_repo(repo, db)
    return ServeState(repo, db)


def seed_run(state: ServeState, session="impact-abc123") -> str:
    log = state.runlog
    log.start(session, "impact", {"seeds": ["pkg.lib._internal"]})
    hook = log.turn_hook(session)
    hook("verify_gate", {
        "seeds": ["pkg.lib._internal"], "rings_done": 1,
        "verified": [{"qualname": "pkg.lib.helper", "depth": 1,
                      "via": "pkg.lib._internal", "edge_kind": "calls", "why": "w"}],
        "dropped": [{"qualname": "pkg.fake", "reason": "edge not found in graph"}],
    })
    hook("synthesize", {
        "seeds": ["pkg.lib._internal"], "rings_done": 2,
        "verified": [
            {"qualname": "pkg.lib.helper", "depth": 1, "via": "pkg.lib._internal",
             "edge_kind": "calls", "why": "w"},
            {"qualname": "app.main", "depth": 2, "via": "pkg.lib.helper",
             "edge_kind": "calls", "why": "w"},
        ],
        "dropped": [], "draft": "# report",
    })
    log.finish(session, {"closure_recall": 1.0}, "approved")
    return session


def test_runlog_roundtrip_and_sessions(state):
    session = seed_run(state)
    events = state.runlog.read(session)
    assert [e["kind"] for e in events] == ["start", "turn", "turn", "finish"]
    (summary,) = state.runlog.sessions()
    assert summary["session_id"] == session
    assert summary["workflow"] == "impact"
    assert summary["outcome"] == "approved"
    # incremental read for live polling
    assert [e["kind"] for e in state.runlog.read(session, after=2)] == ["turn", "finish"]


def test_impact_model_assembles_final_state(state):
    session = seed_run(state)
    model = state.impact_model(session)
    assert model["rings"] == 2
    assert {c["qualname"] for c in model["verified"]} == {"pkg.lib.helper", "app.main"}
    assert model["outcome"] == "approved"
    assert model["scores"]["closure_recall"] == 1.0
    # dropped claims from mid-run turns are superseded by the final turn —
    # the final ledger shows the run's end state
    assert model["dropped"] == []


def test_graph_and_symbol_endpoints_shape(state):
    g = state.graph()
    assert any(n["qualname"] == "pkg.lib.helper" for n in g["nodes"])
    assert any(e["kind"] == "calls" for e in g["edges"])
    sym = state.symbol("pkg.lib.helper")
    assert "app.main" in sym["dependents"]
    assert state.symbol("lib.helper")["qualname"] == "pkg.lib.helper"  # suffix
    assert state.symbol("nope.nothing") is None


def test_http_routes_end_to_end(state):
    session = seed_run(state)
    httpd = make_server(state.repo_root, state.db_path, port=0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        def get(path):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
                return json.load(r)

        assert get("/api/meta")["stats"]["files"] >= 4
        assert get(f"/api/impact?id={session}")["rings"] == 2
        assert get("/api/runs")[0]["session_id"] == session
        assert get("/api/ladder")["invariants"] == []  # no gusset.toml in fixture
        # static index exists
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
            assert r.status == 200
        # traversal is refused
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/../pyproject.toml")
            refused = False
        except urllib.error.HTTPError as e:
            refused = e.code == 404
        assert refused
    finally:
        httpd.shutdown()


def test_post_csrf_defenses(state):
    """Cross-origin form POSTs must be refused; .env injection blocked."""
    httpd = make_server(state.repo_root, state.db_path, port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/api/setup"

    def post(data, headers):
        req = urllib.request.Request(base, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    try:
        # form content type (what a cross-origin <form> sends) → 415
        assert post(b"a=1", {"Content-Type": "application/x-www-form-urlencoded"}) == 415
        # non-local Origin → 403
        assert post(b"{}", {"Content-Type": "application/json",
                            "Origin": "https://evil.example"}) == 403
        # newline smuggling into .env → 400
        body = json.dumps({"action": "write",
                           "keys": {"anthropic": "x\nEVIL=1"}}).encode()
        assert post(body, {"Content-Type": "application/json"}) == 400
        # legitimate local write still works
        body = json.dumps({"action": "write", "keys": {"anthropic": "sk-ok"}}).encode()
        assert post(body, {"Content-Type": "application/json",
                           "Origin": f"http://127.0.0.1:{port}"}) == 200
    finally:
        httpd.shutdown()


def test_allowlist_and_doc_excerpt(state):
    # allowlist: idempotent append, validation, drift respects it
    assert state.allowlist_get() == {"entries": []}
    state.allowlist_add("asyncio.to_thread")
    state.allowlist_add("asyncio.to_thread")  # idempotent
    assert state.allowlist_get()["entries"] == ["asyncio.to_thread"]
    with pytest.raises(ValueError):
        state.allowlist_add("../etc/passwd")
    from gusset.workflows.docsdrift import load_allowlist

    assert "asyncio.to_thread" in load_allowlist(state.repo_root)

    # doc excerpt: in-repo docs only, correct window
    (state.repo_root / "notes.md").write_text(
        "\n".join(f"line {i}" for i in range(1, 21)) + "\n"
    )
    ex = state.doc_excerpt("notes.md", 10)
    assert ex["start"] == 4 and "line 10" in ex["lines"]
    assert state.doc_excerpt("../pyproject.toml", 1) is None  # traversal refused


def test_setup_write_env_merges_and_gitignores(state):
    env = state.repo_root / ".env"
    env.write_text("EXISTING=1\nANTHROPIC_API_KEY=old\n")
    path = state.write_env({"anthropic": "sk-ant-new", "latchkey": "lk_live_x"})
    text = Path(path).read_text()
    assert "EXISTING=1" in text                      # unrelated lines kept
    assert "ANTHROPIC_API_KEY=sk-ant-new" in text    # replaced in place
    assert text.count("ANTHROPIC_API_KEY") == 1
    assert "LATCHKEY_TOKEN=lk_live_x" in text
    assert ".env" in (state.repo_root / ".gitignore").read_text()
    assert (Path(path).stat().st_mode & 0o777) == 0o600  # owner-only secrets


def test_cli_impact_writes_runlog(tmp_path):
    """The impact command's turn hook chain must land events on disk."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    db = repo / ".gusset" / "graph.db"
    db.parent.mkdir(parents=True)
    index_repo(repo, db)
    # run via the fake-model path: cheaper to exercise RunLog directly through
    # the workflow with the logged hook, mirroring cli wiring
    import asyncio

    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.workflows.impact import build_impact_graph

    log = RunLog(db.parent / "runs")
    session = "impact-clitest"
    log.start(session, "impact", {})
    model = FakeMessagesListChatModel(responses=[AIMessage(content=json.dumps({"explanations": []}))] * 3 + [AIMessage(content="s")])
    with SqliteSaver.from_conn_string(str(tmp_path / "c.db")) as saver:
        graph = build_impact_graph(model, checkpointer=saver,
                                   turn_hook=log.turn_hook(session))
        config = {"configurable": {"thread_id": session}}
        graph.invoke({"db_path": str(db), "seed_qualnames": ["pkg.lib._internal"]}, config)
        graph.invoke(Command(resume=True), config)
    log.finish(session, {"closure_recall": 1.0}, "approved")
    kinds = [e["kind"] for e in log.read(session)]
    assert kinds[0] == "start" and kinds[-1] == "finish"
    assert kinds.count("turn") >= 3
