"""The serve API: read-only JSON over Gusset's state, plus the one write
(setup -> .env). Stdlib http.server on 127.0.0.1 only — a fork-and-run
tool doesn't get to demand a web framework, and local-only is a security
property, not a limitation.

Endpoints (all GET unless noted):
  /api/meta            repo, commit, counts
  /api/graph           nodes + edges for the explorer (trimmed for size)
  /api/symbol?q=       symbol detail: dependents/dependencies
  /api/runs            run list (newest first)
  /api/run?id=&after=  events for one run (poll with `after` for live)
  /api/impact?id=      assembled impact-replay model for a finished run
  /api/ladder          invariants, levels, per-run history, ledger events
  /api/drift?id=       latest docs-drift result
  /api/setup  POST     validate keys live / write .env
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from gusset.graph import GraphStore
from gusset.serve.events import RunLog, runs_dir


class ServeState:
    def __init__(self, repo_root: Path, db_path: Path):
        self.repo_root = repo_root
        self.db_path = db_path
        # Beside the DB, because that is where every CLI workflow writes it
        # (`RunLog(db.parent / "runs")`). Deriving it from the repo root
        # instead agreed with the writers only for the default
        # `.gusset/graph.db`; point `--db` anywhere else — a foreign repo,
        # or any setup that keeps the graph out of the tree — and the runs,
        # ladder and drift views were permanently empty while the graph
        # view worked, with nothing to indicate why.
        self.runlog = RunLog(runs_dir(db_path))

    def store(self) -> GraphStore:
        return GraphStore(self.db_path)

    # -- view models ---------------------------------------------------------

    def meta(self) -> dict:
        store = self.store()
        try:
            stats = store.stats()
        finally:
            store.close()
        return {
            "repo": self.repo_root.name,
            "stats": stats,
        }

    def graph(self, max_nodes: int = 2000) -> dict:
        store = self.store()
        try:
            conn = store.conn
            nodes = [
                {
                    "id": r["id"], "name": r["name"], "qualname": r["qualname"],
                    "kind": r["kind"], "path": r["path"],
                }
                for r in conn.execute(
                    """SELECT s.id, s.name, s.qualname, s.kind, f.path
                       FROM symbols s JOIN files f ON f.id = s.file_id
                       LIMIT ?""", (max_nodes,)
                )
            ]
            edges = [
                {"source": r["src"], "target": r["dst"], "kind": r["kind"]}
                for r in conn.execute(
                    "SELECT DISTINCT src, dst, kind FROM edges LIMIT ?",
                    (max_nodes * 4,),
                )
            ]
        finally:
            store.close()
        return {"nodes": nodes, "edges": edges}

    def symbol(self, qualname: str) -> dict | None:
        store = self.store()
        try:
            sym = store.symbol_by_qualname(qualname)
            if sym is None:
                hits = store.symbols_by_qualname_suffix(qualname)
                sym = hits[0] if len(hits) == 1 else None
            if sym is None:
                return None
            return {
                "id": sym.id, "qualname": sym.qualname, "kind": sym.kind,
                "path": sym.path, "line": sym.start_line,
                "dependents": [s.qualname for s in store.dependents(sym.id)],
                "dependencies": [s.qualname for s in store.dependencies(sym.id)],
            }
        finally:
            store.close()

    def impact_model(self, session_id: str) -> dict:
        """Everything the impact-replay view renders, from the event log."""
        events = self.runlog.read(session_id)
        turns = [e for e in events if e["kind"] == "turn"]
        finish = next((e for e in reversed(events) if e["kind"] == "finish"), None)
        last = turns[-1] if turns else {}
        verified = last.get("verified") or []
        dropped = last.get("dropped") or []
        seeds = last.get("seeds") or []
        # positions are the frontend's job (force layout); we ship structure
        return {
            "session_id": session_id,
            "seeds": seeds,
            "verified": verified,
            "dropped": dropped,
            "rings": max((c.get("depth", 0) for c in verified), default=0),
            "turns": [
                {"seq": t["seq"], "ts": t["ts"], "node": t["node"],
                 "verified_n": _n(t.get("verified")), "dropped_n": _n(t.get("dropped"))}
                for t in turns
            ],
            "scores": (finish or {}).get("scores"),
            "outcome": (finish or {}).get("outcome", "running"),
        }

    def ladder(self) -> dict:
        from gusset.supervisor.config import load_config
        from gusset.supervisor.ladder import Ladder

        ledger_path = self.repo_root / ".gusset" / "ladder.jsonl"
        entries = []
        if ledger_path.exists():
            for line in ledger_path.read_text().splitlines():
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        invariants = []
        toml = self.repo_root / "gusset.toml"
        if toml.exists():
            cfg = load_config(toml)
            lad = Ladder(ledger_path)
            for inv in cfg.invariants:
                runs = [e for e in entries
                        if e.get("invariant") == inv.name and e.get("type") == "run"]
                invariants.append({
                    "name": inv.name,
                    "workflow": inv.workflow,
                    "trigger": inv.trigger,
                    "level": str(lad.current_level(inv.name, inv.autonomy)),
                    "ceiling": str(inv.max_autonomy),
                    "runs": [{"ts": r.get("ts"), "min_score": r.get("min_score"),
                              "scores": r.get("scores")} for r in runs[-20:]],
                })
        return {"invariants": invariants, "ledger": entries[-100:]}

    def drift(self, session_id: str | None) -> dict:
        if session_id is None:
            drift_runs = [s for s in self.runlog.sessions()
                          if s["workflow"] in ("docsdrift", "docs-drift")]
            if not drift_runs:
                return {"claims": [], "stale": [], "session_id": None}
            session_id = drift_runs[0]["session_id"]
        events = self.runlog.read(session_id)
        turns = [e for e in events if e["kind"] == "turn"]
        last = turns[-1] if turns else {}
        # Three buckets, reported separately. The UI used to derive
        # "resolves" as checked - stale, which silently counted every
        # unanchored reference as a verified one: on a repo with 201
        # references, 3 valid and 192 unanchored, it claimed 195 resolve.
        return {
            "session_id": session_id,
            "stale": last.get("stale") or [],
            "claims_checked": last.get("claims"),
            "valid_count": _as_count(last.get("valid")),
            "unanchored_count": _as_count(last.get("unanchored")) or 0,
        }

    # -- drift actions -------------------------------------------------------

    def allowlist_get(self) -> dict:
        from gusset.workflows.docsdrift import load_allowlist

        return {"entries": sorted(load_allowlist(self.repo_root))}

    def allowlist_add(self, symbol: str) -> dict:
        """Append a dotted path to the drift allowlist (idempotent)."""
        import re

        from gusset.workflows.docsdrift import ALLOWLIST_FILE, load_allowlist

        if not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+", symbol):
            raise ValueError(f"not a dotted symbol path: {symbol!r}")
        entries = load_allowlist(self.repo_root)
        if symbol not in entries:
            path = self.repo_root / ALLOWLIST_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            header = (
                "" if path.exists()
                else "# Symbols legitimately outside the graph (stdlib, external\n"
                     "# APIs, concepts). docs-drift skips these. One per line.\n"
            )
            with path.open("a") as f:
                f.write(header + symbol + "\n")
        return {"entries": sorted(entries | {symbol})}

    def doc_excerpt(self, doc: str, line: int, context: int = 6) -> dict | None:
        """A few lines of a doc around a stale reference — read-only, and
        confined to the repo root (no traversal)."""
        target = (self.repo_root / doc).resolve()
        if not target.is_file() or self.repo_root.resolve() not in target.parents:
            return None
        lines = target.read_text(errors="replace").splitlines()
        lo = max(0, line - 1 - context)
        hi = min(len(lines), line + context)
        return {
            "doc": doc, "line": line, "start": lo + 1,
            "lines": lines[lo:hi],
        }

    # -- setup ---------------------------------------------------------------

    def validate_keys(self, keys: dict) -> dict:
        """Live-check each provided key. Never logged, never stored here."""
        out: dict[str, dict] = {}
        if v := keys.get("anthropic"):
            out["anthropic"] = _check_http(
                "https://api.anthropic.com/v1/models",
                {"x-api-key": v, "anthropic-version": "2023-06-01"},
            )
        if v := keys.get("pandaprobe"):
            out["pandaprobe"] = _check_http(
                "https://api.pandaprobe.com/traces?limit=1",
                {"X-API-Key": v,
                 "X-Project-Name": keys.get("pandaprobe_project") or "default"},
            )
        if v := keys.get("latchkey"):
            out["latchkey"] = _check_http(
                "https://api.latchkey.dev/v1/jobs/gusset-setup-probe",
                {"Authorization": f"Bearer {v}"},
                ok_statuses={200, 404},   # 404 with auth = key valid (CLI's trick)
            )
        return out

    def write_env(self, keys: dict) -> str:
        """Merge validated keys into .env without clobbering unrelated lines."""
        env_path = self.repo_root / ".env"
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        updates = {}
        if v := keys.get("anthropic"):
            updates["ANTHROPIC_API_KEY"] = v
        if v := keys.get("pandaprobe"):
            updates["PANDAPROBE_API_KEY"] = v
        if v := keys.get("pandaprobe_project"):
            updates["PANDAPROBE_PROJECT_NAME"] = v
        if v := keys.get("latchkey"):
            updates["LATCHKEY_TOKEN"] = v
        if v := keys.get("repair_model"):
            updates["HARNESS_REPAIR_MODEL"] = v
        seen = set()
        for i, line in enumerate(lines):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                lines[i] = f"{key}={updates[key]}"
                seen.add(key)
        for key, value in updates.items():
            if key not in seen:
                lines.append(f"{key}={value}")
        # Secrets file: atomic replace with owner-only permissions.
        data = ("\n".join(lines) + "\n").encode()
        tmp = env_path.with_suffix(".env.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        os.replace(tmp, env_path)
        os.chmod(env_path, 0o600)
        _ensure_gitignored(self.repo_root, ".env")
        return str(env_path)


def _n(x) -> int:
    return len(x) if isinstance(x, list) else 0


def _as_count(x) -> int | None:
    """Turn payloads store these as counts; tolerate a raw list too."""
    if isinstance(x, int):
        return x
    if isinstance(x, list):
        return len(x)
    return None


def _check_http(url: str, headers: dict, ok_statuses: set | None = None) -> dict:
    ok_statuses = ok_statuses or {200}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": resp.status in ok_statuses, "status": resp.status}
    except urllib.error.HTTPError as e:  # noqa: PERF203
        detail = ""
        try:
            body = e.read(500).decode("utf-8", "replace")
            detail = json.loads(body).get("error", {}).get("message", "")[:120]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": e.code in ok_statuses, "status": e.code, "detail": detail}
    except OSError as e:
        return {"ok": False, "status": 0, "detail": str(e)[:120]}


def _ensure_gitignored(root: Path, entry: str) -> None:
    gi = root / ".gitignore"
    existing = gi.read_text().splitlines() if gi.exists() else []
    if entry not in existing:
        with gi.open("a") as f:
            f.write(f"{entry}\n")
