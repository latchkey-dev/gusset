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


def _symbol(row: sqlite3.Row) -> Symbol:
    return Symbol(
        id=row["id"],
        path=row["path"],
        name=row["name"],
        qualname=row["qualname"],
        kind=row["kind"],
        start_line=row["start_line"],
        end_line=row["end_line"],
    )


_SYMBOL_SELECT = """
SELECT s.id, f.path, s.name, s.qualname, s.kind, s.start_line, s.end_line
FROM symbols s JOIN files f ON f.id = s.file_id
"""


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
        dunder methods (called by the runtime), and `main` (entry points).
        """
        rows = self.conn.execute(
            _SYMBOL_SELECT
            + """
            WHERE s.kind != 'module'
              AND s.name NOT LIKE '\\_\\_%' ESCAPE '\\'
              AND s.name != 'main'
              AND s.id NOT IN (SELECT dst FROM edges)
            ORDER BY f.path, s.start_line
            """
        ).fetchall()
        return [_symbol(r) for r in rows]

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
            "meta": meta,
        }
