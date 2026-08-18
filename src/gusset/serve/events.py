"""Run-event log: the append-only JSONL feed the serve views replay.

Workflows already expose a turn-hook seam; RunLog turns it into durable
events under .gusset/runs/<session_id>.jsonl. One file per run keeps
tail-follow trivial (the live view polls the newest file) and makes a
run shareable by copying one file.

No LLM content is interpreted here — events carry what the workflow
state already held. Writes are line-atomic (single write() of one line).
"""

from __future__ import annotations

import json
import time
from pathlib import Path


class RunLog:
    def __init__(self, root: str | Path = ".gusset/runs"):
        self.root = Path(root)

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.jsonl"

    def append(self, session_id: str, kind: str, payload: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {"ts": time.time(), "kind": kind, **payload}, default=str
        )
        with self.path_for(session_id).open("a") as f:
            f.write(line + "\n")

    # -- the seam adapter ----------------------------------------------------

    def turn_hook(self, session_id: str, inner_hook=None):
        """A turn_hook that logs, then chains to another hook (selfheal's).

        Trims state to view-relevant fields; verified/dropped lists carry
        full claim dicts because the impact replay renders them.
        """

        def hook(node: str, state: dict) -> None:
            self.append(session_id, "turn", {
                "node": node,
                "seeds": state.get("seeds"),
                "rings_done": state.get("rings_done"),
                "verified": state.get("verified"),
                "dropped": state.get("dropped"),
                "stale": state.get("stale"),
                "claims": _count(state.get("claims")),
                "has_draft": bool(state.get("draft")),
            })
            if inner_hook is not None:
                inner_hook(node, state)

        return hook

    def start(self, session_id: str, workflow: str, meta: dict | None = None) -> None:
        self.append(session_id, "start", {"workflow": workflow, **(meta or {})})

    def finish(self, session_id: str, scores: dict | None, outcome: str) -> None:
        self.append(session_id, "finish", {"scores": scores, "outcome": outcome})

    # -- read side -----------------------------------------------------------

    def sessions(self, limit: int = 50) -> list[dict]:
        """Newest-first run summaries. Limit is clamped to protect the UI."""
        limit = max(1, min(limit, 200))
        if not self.root.exists():
            return []
        files = sorted(
            self.root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:limit]
        out = []
        for f in files:
            events = self.read(f.stem)
            start = next((e for e in events if e["kind"] == "start"), {})
            finish = next((e for e in reversed(events) if e["kind"] == "finish"), None)
            out.append({
                "session_id": f.stem,
                "workflow": start.get("workflow") or f.stem.split("-")[0],
                "started": events[0]["ts"] if events else None,
                "events": len(events),
                "outcome": (finish or {}).get("outcome", "running"),
                "scores": (finish or {}).get("scores"),
            })
        return out

    def read(self, session_id: str, after: int = 0) -> list[dict]:
        """Events for a session, optionally only those after line `after`."""
        path = self.path_for(session_id)
        if not path.exists():
            return []
        events = []
        for i, line in enumerate(path.read_text().splitlines()):
            if i < after or not line.strip():
                continue
            try:
                events.append({"seq": i, **json.loads(line)})
            except json.JSONDecodeError:
                continue  # torn tail line during a live write; next poll gets it
        return events


def _count(x) -> int | None:
    return len(x) if isinstance(x, list) else None
