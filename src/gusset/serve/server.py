"""HTTP layer for gusset serve: routes -> ServeState, static frontend.

127.0.0.1 only. The one non-GET route is /api/setup (writes .env locally).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gusset.serve.api import ServeState

STATIC_DIR = Path(__file__).parent / "static"
_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
          ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2"}


def make_handler(state: ServeState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: ARG002 — quiet by default
            pass

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
                return self._static(route)
            except Exception as exc:  # noqa: BLE001 — surface, don't crash the server
                return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/setup":
                return self._json({"error": "not found"}, 404)
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json({"error": "bad json"}, 400)
            keys = body.get("keys") or {}
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
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    return httpd
