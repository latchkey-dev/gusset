"""Heartbeat tests: file-tail semantics and end-to-end SSE delivery."""

import json
import shutil
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from gusset.graph.indexer import index_repo
from gusset.serve.events import RunLog
from gusset.serve.heartbeat import Heartbeat
from gusset.serve.server import serve as make_server

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


def wait_for(q, kinds, timeout=5.0):
    """Collect events from the queue until all kinds seen or timeout."""
    seen = []
    deadline = time.time() + timeout
    while time.time() < deadline and not all(
        any(e.get("kind") == k for e in seen) for k in kinds
    ):
        try:
            seen.append(q.get(timeout=0.3))
        except Exception:  # noqa: BLE001
            continue
    return seen


def test_watcher_only_streams_new_events(tmp_path):
    runs = tmp_path / "runs"
    log = RunLog(runs)
    log.start("impact-old", "impact", {})       # history before start()
    hb = Heartbeat(runs)
    hb.start()
    time.sleep(0.4)
    q = hb.subscribe()
    log.start("impact-new", "impact", {"seeds": ["x"]})
    log.append("impact-new", "turn", {"node": "verify_gate"})
    events = wait_for(q, {"start", "turn"})
    sessions = {e["session_id"] for e in events}
    assert "impact-new" in sessions
    assert "impact-old" not in sessions          # history not replayed
    kinds = [e["kind"] for e in events if e["session_id"] == "impact-new"]
    assert kinds == ["start", "turn"]            # ordered


def test_signal_events_flow_but_stay_out_of_sessions(tmp_path):
    runs = tmp_path / "runs"
    hb = Heartbeat(runs)
    hb.start()
    q = hb.subscribe()
    log = RunLog(runs)
    log.signal("index", {"symbols": 42})
    events = wait_for(q, {"index"})
    assert any(e["kind"] == "index" and e["session_id"] == "_signals"
               for e in events)
    assert log.sessions() == []                  # signals never list as runs


def test_partial_line_not_emitted_until_complete(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    hb = Heartbeat(runs)
    hb.start()
    q = hb.subscribe()
    f = runs / "impact-x.jsonl"
    with f.open("a") as fh:
        fh.write('{"kind": "turn", "ts": 1')     # torn write, no newline
        fh.flush()
        time.sleep(0.6)
        assert q.empty()                         # nothing half-parsed
        fh.write(', "node": "verify_gate"}\n')
    events = wait_for(q, {"turn"})
    assert events and events[0]["node"] == "verify_gate"


def test_sse_end_to_end(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    db = repo / ".gusset" / "graph.db"
    db.parent.mkdir(parents=True)
    index_repo(repo, db)
    httpd = make_server(repo, db, port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    received = []

    def listen():
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/events")
        with urllib.request.urlopen(req, timeout=10) as resp:
            for raw in resp:
                line = raw.decode().strip()
                if line.startswith("data: "):
                    received.append(json.loads(line[6:]))
                    if len(received) >= 2:
                        return

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.8)                               # let SSE connect + watcher arm
    log = RunLog(repo / ".gusset" / "runs")
    log.start("impact-sse", "impact", {})
    log.append("impact-sse", "turn", {"node": "synthesize"})
    t.join(timeout=8)
    httpd.shutdown()
    assert [e["kind"] for e in received] == ["start", "turn"]
    assert received[0]["workflow"] == "impact"
