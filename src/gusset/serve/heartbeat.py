"""The heartbeat: live CLI → browser sync over Server-Sent Events.

A background watcher polls the runs directory (250ms — mtime+size checks,
cheap) and pushes every NEW event line to connected SSE clients. The
frontend reacts: a `start` event navigates to the workflow's tab, `turn`
events live-update the view, `finish` completes it, and `signal` events
(index finished) refresh static views.

Why SSE and not WebSockets: stdlib http.server can hold a streaming
response with zero new dependencies, auto-reconnect is built into
EventSource, and traffic is strictly one-way — the browser never needs
to talk back on this channel.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path


class Heartbeat:
    def __init__(self, runs_root: Path):
        self.root = Path(runs_root)
        self._clients: set[queue.Queue] = set()
        self._lock = threading.Lock()
        # session file -> (inode, bytes consumed): the inode detects a file
        # deleted and recreated at the same size (live-verify find — the
        # watcher went silent on recreated sessions with equal byte counts).
        self._offsets: dict[str, tuple[int, int]] = {}
        self._started = False

    # -- client side ---------------------------------------------------------

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._clients.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(q)

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    # -- watcher -------------------------------------------------------------

    def start(self) -> None:
        """Idempotent; begins tailing from the CURRENT end of every file so
        a fresh browser only sees genuinely new activity, not history."""
        if self._started:
            return
        self._started = True
        if self.root.exists():
            for f in self.root.glob("*.jsonl"):
                st = f.stat()
                self._offsets[f.name] = (st.st_ino, st.st_size)
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        while True:
            try:
                self._scan()
            except OSError:
                pass  # transient fs weather; next tick retries
            time.sleep(0.25)

    def _scan(self) -> None:
        if not self.root.exists():
            return
        for f in sorted(self.root.glob("*.jsonl")):
            st = f.stat()
            ino, size = st.st_ino, st.st_size
            known_ino, offset = self._offsets.get(f.name, (ino, 0))
            if ino != known_ino:             # deleted + recreated: fresh file
                offset = 0
            if size <= offset:
                if size < offset:            # truncated/rotated: restart
                    self._offsets[f.name] = (ino, 0)
                else:
                    self._offsets[f.name] = (ino, offset)
                continue
            with f.open("rb") as fh:
                fh.seek(offset)
                chunk = fh.read(size - offset)
            # only complete lines; carry partial tail to the next tick
            consumed = chunk.rfind(b"\n") + 1
            if consumed == 0:
                self._offsets[f.name] = (ino, offset)
                continue
            self._offsets[f.name] = (ino, offset + consumed)
            session_id = f.stem
            for line in chunk[:consumed].splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._publish({"session_id": session_id, **event})

    def _publish(self, event: dict) -> None:
        with self._lock:
            dead = []
            for q in self._clients:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)   # stalled client: drop it, EventSource reconnects
            for q in dead:
                self._clients.discard(q)
