"""HTTP layer for gusset serve: routes -> ServeState, static frontend.

127.0.0.1 only. The one non-GET route is /api/setup (writes .env locally).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gusset.serve.api import ServeState
from gusset.serve.heartbeat import Heartbeat

STATIC_DIR = Path(__file__).parent / "static"
_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
          ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2"}


def make_handler(state: ServeState, heartbeat: Heartbeat | None = None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: ARG002 — quiet by default
            pass

        def _sse(self) -> None:
            """The heartbeat stream: one `data:` frame per run event, plus a
            15s keepalive comment so proxies and the client never time out."""
            if heartbeat is None:
                return self._json({"error": "heartbeat disabled"}, 404)
            q = heartbeat.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                import queue as _q

                while True:
                    try:
                        event = q.get(timeout=15)
                        payload = json.dumps(event).encode()
                        self.wfile.write(b"data: " + payload + b"\n\n")
                    except _q.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass  # browser navigated away; EventSource reconnects if open
            finally:
                heartbeat.unsubscribe(q)

        def _json(self, payload, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            route = url.path
            try:
                if route == "/api/events":
                    return self._sse()
                if route == "/api/meta":
                    return self._json(state.meta())
                if route == "/api/graph":
                    return self._json(state.graph())
                if route == "/api/symbol":
                    sym = state.symbol(q.get("q", ""))
                    return self._json(sym or {"error": "not found"},
                                      200 if sym else 404)
                if route == "/api/runs":
                    return self._json(state.runlog.sessions())
                if route == "/api/run":
                    return self._json(state.runlog.read(
                        q.get("id", ""), after=int(q.get("after", 0))))
                if route == "/api/impact":
                    return self._json(state.impact_model(q.get("id", "")))
                if route == "/api/ladder":
                    return self._json(state.ladder())
                if route == "/api/drift":
                    return self._json(state.drift(q.get("id")))
                if route == "/api/allowlist":
                    return self._json(state.allowlist_get())
                if route == "/api/doc":
                    ex = state.doc_excerpt(q.get("doc", ""), int(q.get("line", 1)))
                    return self._json(ex or {"error": "not found"},
                                      200 if ex else 404)
                return self._static(route)
            except Exception as exc:  # noqa: BLE001 — surface, don't crash the server
                return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

        def do_POST(self) -> None:  # noqa: N802
            route = urlparse(self.path).path
            if route not in ("/api/setup", "/api/allowlist"):
                return self._json({"error": "not found"}, 404)
            # CSRF hardening: a malicious page can form-POST to localhost
            # without CORS ever blocking it. Require JSON content type
            # (unsettable by cross-origin forms without a preflight, which
            # this server never approves) and a local Origin when present.
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            if ctype != "application/json":
                return self._json({"error": "content-type must be application/json"}, 415)
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
                return self._json({"error": "cross-origin request refused"}, 403)
            # Host check defeats DNS rebinding (attacker domain resolving to
            # 127.0.0.1 carries its own hostname in Host, not ours).
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):
                return self._json({"error": "host not local"}, 403)
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json({"error": "bad json"}, 400)
            if route == "/api/allowlist":
                try:
                    return self._json(state.allowlist_add(str(body.get("symbol", ""))))
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
            keys = body.get("keys") or {}
            if any("\n" in str(v) or "\r" in str(v) for v in keys.values()):
                return self._json({"error": "key values must be single-line"}, 400)
            try:
                if body.get("action") == "write":
                    path = state.write_env(keys)
                    return self._json({"written": path})
                return self._json({"validation": state.validate_keys(keys)})
            except Exception as exc:  # noqa: BLE001
                return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

        def _static(self, route: str) -> None:
            rel = "index.html" if route in ("/", "") else route.lstrip("/")
            target = (STATIC_DIR / rel).resolve()
            if not target.is_file() or STATIC_DIR.resolve() not in target.parents:
                return self._json({"error": "not found"}, 404)
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             _TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(repo_root: Path, db_path: Path, port: int = 8321) -> ThreadingHTTPServer:
    state = ServeState(repo_root, db_path)
    heartbeat = Heartbeat(repo_root / ".gusset" / "runs")
    heartbeat.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state, heartbeat))
    return httpd
