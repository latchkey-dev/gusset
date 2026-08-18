"""GraphStore: the query API over the code graph.

Every workflow claim gets verified through this API, so it is the oracle's
ground truth. Queries are deterministic SQL — no LLM anywhere in this module.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from gusset.graph.schema import connect


@dataclass
class Symbol:
    id: int
    path: str
    name: str
    qualname: str
    kind: str
    start_line: int
    end_line: int
    version: str | None = None  # packages only; None for code symbols


def _symbol(row: sqlite3.Row) -> Symbol:
    return Symbol(
        id=row["id"],
        path=row["path"],
        name=row["name"],
        qualname=row["qualname"],
        kind=row["kind"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        version=row["version"],
    )


_SYMBOL_SELECT = """
SELECT s.id, f.path, s.name, s.qualname, s.kind, s.start_line, s.end_line,
       s.version
FROM symbols s JOIN files f ON f.id = s.file_id
"""


def cluster_key(path: str) -> str:
    """Deterministic module-cluster key for a repo-relative POSIX path.

    Files under a directory cluster by their top-level directory (the
    package); root-level files cluster by their stem: ``pkg/lib.py`` -> "pkg",
    ``app.py`` -> "app". Paths in this store are always POSIX (schema.py), so
    splitting on "/" is exact, not a heuristic.
    """
    if "/" in path:
        return path.split("/", 1)[0]
    return path.rsplit(".", 1)[0] if "." in path else path


class GraphStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = connect(db_path)

    def close(self) -> None:
        self.conn.close()

    # -- lookups ------------------------------------------------------------

    def symbol_by_qualname(self, qualname: str) -> Symbol | None:
        row = self.conn.execute(
            _SYMBOL_SELECT + "WHERE s.qualname = ?", (qualname,)
        ).fetchone()
        return _symbol(row) if row else None

    def symbols_by_name(self, name: str) -> list[Symbol]:
        rows = self.conn.execute(
            _SYMBOL_SELECT + "WHERE s.name = ?", (name,)
        ).fetchall()
        return [_symbol(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> list[Symbol]:
        rows = self.conn.execute(
            _SYMBOL_SELECT
            + "WHERE s.id IN (SELECT rowid FROM symbols_fts WHERE symbols_fts MATCH ?) "
            "LIMIT ?",
            (query, limit),
        ).fetchall()
        return [_symbol(r) for r in rows]

    def symbols_overlapping(self, path: str, lines: set[int]) -> list[Symbol]:
        """Non-module symbols in `path` whose span overlaps any of `lines`.

        Maps a diff hunk to the symbols it touches — the seeds of an impact run.
        """
        rows = self.conn.execute(
            _SYMBOL_SELECT + "WHERE f.path = ? AND s.kind != 'module'", (path,)
        ).fetchall()
        return [
            _symbol(r)
            for r in rows
            if any(r["start_line"] <= n <= r["end_line"] for n in lines)
        ]

    def symbols_by_qualname_suffix(self, suffix: str) -> list[Symbol]:
        """Symbols whose qualname equals `suffix` or ends with ".<suffix>".

        Deterministic resolution for doc-style dotted references, where docs
        routinely abbreviate leading packages (`lib.helper` resolves to
        pkg.lib.helper). GLOB rather than LIKE so `_` stays a literal and
        matching stays case-sensitive; callers pass dotted identifier paths
        (word characters and dots), which contain no GLOB metacharacters.
        """
        rows = self.conn.execute(
            _SYMBOL_SELECT
            + "WHERE s.qualname = ? OR s.qualname GLOB ('*.' || ?) "
            "ORDER BY s.qualname",
            (suffix, suffix),
        ).fetchall()
        return [_symbol(r) for r in rows]

    def symbol_by_id(self, symbol_id: int) -> Symbol | None:
        row = self.conn.execute(
            _SYMBOL_SELECT + "WHERE s.id = ?", (symbol_id,)
        ).fetchone()
        return _symbol(row) if row else None

    def edges_between(self, src_id: int, dst_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT kind, line FROM edges WHERE src = ? AND dst = ?", (src_id, dst_id)
        ).fetchall()
        return [{"kind": r["kind"], "line": r["line"]} for r in rows]

    def edge_exists(self, src_qualname: str, dst_qualname: str, kind: str | None = None) -> bool:
        """The oracle's core primitive: does this claimed relationship exist?"""
        sql = """
        SELECT 1 FROM edges e
        JOIN symbols a ON a.id = e.src
        JOIN symbols b ON b.id = e.dst
        WHERE a.qualname = ? AND b.qualname = ?
        """
        params: list[str] = [src_qualname, dst_qualname]
        if kind is not None:
            sql += " AND e.kind = ?"
            params.append(kind)
        return self.conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    # -- traversals ---------------------------------------------------------

    def dependents(self, symbol_id: int) -> list[Symbol]:
        """Direct dependents: symbols with an edge INTO this one (who uses X)."""
        rows = self.conn.execute(
            _SYMBOL_SELECT + "WHERE s.id IN (SELECT src FROM edges WHERE dst = ?)",
            (symbol_id,),
        ).fetchall()
        return [_symbol(r) for r in rows]

    def dependencies(self, symbol_id: int) -> list[Symbol]:
        """Direct dependencies: symbols this one has an edge TO (what X uses)."""
        rows = self.conn.execute(
            _SYMBOL_SELECT + "WHERE s.id IN (SELECT dst FROM edges WHERE src = ?)",
            (symbol_id,),
        ).fetchall()
        return [_symbol(r) for r in rows]

    def reverse_closure(self, seed_ids: list[int], max_depth: int = 10) -> dict[int, int]:
        """All transitive dependents of the seeds -> {symbol_id: min_depth}.

        This is the impact workflow's ground truth: the set of everything
        that could be affected by changing the seeds. Depth 0 = the seeds.
        """
        if not seed_ids:
            return {}
        placeholders = ",".join("?" * len(seed_ids))
        rows = self.conn.execute(
            f"""
            WITH RECURSIVE closure(id, depth) AS (
                SELECT id, 0 FROM symbols WHERE id IN ({placeholders})
                UNION
                SELECT e.src, c.depth + 1
                FROM edges e JOIN closure c ON e.dst = c.id
                WHERE c.depth < ?
            )
            SELECT id, MIN(depth) AS depth FROM closure GROUP BY id
            """,
            [*seed_ids, max_depth],
        ).fetchall()
        return {row["id"]: row["depth"] for row in rows}

    def dead_symbols(self) -> list[Symbol]:
        """Symbols with no incoming edges — candidates for deletion.

        Conservative exclusions: modules (files are entered externally),
        packages (an unimported dependency is not dead code), dunder
        methods (called by the runtime), and `main` (entry points).
        """
        rows = self.conn.execute(
            _SYMBOL_SELECT
            + """
            WHERE s.kind NOT IN ('module', 'package')
              AND s.name NOT LIKE '\\_\\_%' ESCAPE '\\'
              AND s.name != 'main'
              AND s.id NOT IN (SELECT dst FROM edges)
            ORDER BY f.path, s.start_line
            """
        ).fetchall()
        return [_symbol(r) for r in rows]

    # -- external dependencies ------------------------------------------------

    def packages(self) -> list[Symbol]:
        """All external-dependency nodes (kind='package'), with versions."""
        rows = self.conn.execute(
            _SYMBOL_SELECT + "WHERE s.kind = 'package' ORDER BY s.name"
        ).fetchall()
        return [_symbol(r) for r in rows]

    def package_dependents(self, package_id: int) -> list[Symbol]:
        """Symbols that import this package (via imports_external edges)."""
        rows = self.conn.execute(
            _SYMBOL_SELECT
            + "WHERE s.id IN (SELECT src FROM edges "
            "                 WHERE dst = ? AND kind = 'imports_external')",
            (package_id,),
        ).fetchall()
        return [_symbol(r) for r in rows]

    # -- module-level aggregation -------------------------------------------

    def module_clusters(self) -> dict[str, list[Symbol]]:
        """All symbols grouped into module clusters by cluster_key(file path).

        The deterministic partition shared by the atlas workflow (T1) and the
        oracle's module_coverage score — one truth source, no LLM. Clusters
        are sorted by name; each symbol list is ordered by path, start line,
        then id. A single-file repo yields exactly one cluster. Package
        nodes are excluded — clusters partition the repo's own code, and
        external deps have their own queries (packages, package_dependents).
        """
        rows = self.conn.execute(
            _SYMBOL_SELECT
            + "WHERE s.kind != 'package' ORDER BY f.path, s.start_line, s.id"
        ).fetchall()
        clusters: dict[str, list[Symbol]] = {}
        for r in rows:
            clusters.setdefault(cluster_key(r["path"]), []).append(_symbol(r))
        return dict(sorted(clusters.items()))

    def edge_listing(self) -> list[dict]:
        """Every code-graph edge with both endpoints' qualnames and file paths.

        The substrate for module-level views: cluster_edges() and the atlas
        per-module prompts are built from exactly this list. Deterministic
        ORDER BY, plain SQL, no LLM. imports_external edges are excluded so
        the module views stay a partition of the repo's own code (external
        deps are served by packages()/package_dependents()).
        """
        rows = self.conn.execute(
            """
            SELECT e.kind, e.line,
                   a.qualname AS src_qualname, fa.path AS src_path,
                   b.qualname AS dst_qualname, fb.path AS dst_path
            FROM edges e
            JOIN symbols a ON a.id = e.src JOIN files fa ON fa.id = a.file_id
            JOIN symbols b ON b.id = e.dst JOIN files fb ON fb.id = b.file_id
            WHERE e.kind != 'imports_external'
            ORDER BY fa.path, e.line, a.qualname, b.qualname, e.kind
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def cluster_edges(self) -> list[dict]:
        """Inter-cluster edges: {src, dst, kinds, count} per cluster pair.

        Aggregates edge_listing() by cluster_key of each endpoint's file,
        excluding intra-cluster edges. The atlas Mermaid diagram is drawn
        from exactly this list, so diagram edges are a subset of graph edges
        by construction. Sorted by (src, dst); kinds sorted within each pair.
        """
        agg: dict[tuple[str, str], dict] = {}
        for e in self.edge_listing():
            src = cluster_key(e["src_path"])
            dst = cluster_key(e["dst_path"])
            if src == dst:
                continue
            entry = agg.setdefault(
                (src, dst), {"src": src, "dst": dst, "kinds": set(), "count": 0}
            )
            entry["kinds"].add(e["kind"])
            entry["count"] += 1
        return [
            {**agg[pair], "kinds": sorted(agg[pair]["kinds"])}
            for pair in sorted(agg)
        ]

    # -- stats --------------------------------------------------------------

    def stats(self) -> dict[str, object]:
        c = self.conn
        by_kind = {
            r["kind"]: r["n"]
            for r in c.execute("SELECT kind, COUNT(*) n FROM symbols GROUP BY kind")
        }
        by_edge = {
            r["kind"]: r["n"]
            for r in c.execute("SELECT kind, COUNT(*) n FROM edges GROUP BY kind")
        }
        meta = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM meta")}
        return {
            "files": c.execute("SELECT COUNT(*) n FROM files").fetchone()["n"],
            "symbols": by_kind,
            "edges": by_edge,
            # Explicit keys so they read 0 (not absent) when a repo has no
            # manifests — the external layer's health is always visible.
            "packages": by_kind.get("package", 0),
            "imports_external": by_edge.get("imports_external", 0),
            "meta": meta,
        }
