"""Two-pass repo indexer.

Pass 1: extract every definition in every supported file.
Pass 2: resolve references to definitions and write edges.

Resolution is heuristic by design (no type inference — see docs): same-file
first, then unique global name. Ambiguous or external references are counted
in meta, never guessed into edges — a wrong edge would poison the oracle.
"""

from __future__ import annotations

import hashlib
import posixpath
import subprocess
from pathlib import Path

from gusset.graph.extract import LANGUAGE_BY_SUFFIX, Extraction, extract
from gusset.graph.schema import connect

SKIP_DIRS = {
    ".git", ".hg", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox", ".eggs",
}


def _module_qualname(rel_path: Path) -> str:
    """tests/fixtures pkg/lib.py -> pkg.lib ; pkg/__init__.py -> pkg"""
    parts = list(rel_path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else rel_path.stem


def _git_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except OSError:
        return None


def index_repo(root: str | Path, db_path: str | Path) -> dict[str, int]:
    """Index `root` into `db_path`, replacing any prior index. Returns counts."""
    root = Path(root).resolve()
    conn = connect(db_path)
    cur = conn.cursor()
    for table in ("edges", "symbols", "files", "meta"):
        cur.execute(f"DELETE FROM {table}")

    # (file_id, module_qual, rel_dir, ex)
    extractions: list[tuple[int, str, str, Extraction]] = []
    unresolved = 0

    # -- pass 1: definitions ------------------------------------------------
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in LANGUAGE_BY_SUFFIX:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        language = LANGUAGE_BY_SUFFIX[path.suffix]
        source = path.read_bytes()
        rel = path.relative_to(root)
        cur.execute(
            "INSERT INTO files(path, language, sha) VALUES (?, ?, ?)",
            (rel.as_posix(), language, hashlib.sha256(source).hexdigest()),
        )
        file_id = cur.lastrowid
        module_qual = _module_qualname(rel)
        n_lines = source.count(b"\n") + 1
        cur.execute(
            "INSERT INTO symbols(file_id, name, qualname, kind, start_line, end_line) "
            "VALUES (?, ?, ?, 'module', 1, ?)",
            (file_id, module_qual.rsplit(".", 1)[-1], module_qual, n_lines),
        )
        ex = extract(source, language)
        for d in ex.defs:
            cur.execute(
                "INSERT INTO symbols(file_id, name, qualname, kind, start_line, end_line) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (file_id, d.name, f"{module_qual}.{d.qualname}", d.kind,
                 d.start_line, d.end_line),
            )
        extractions.append((file_id, module_qual, rel.parent.as_posix(), ex))

    # -- resolution maps ----------------------------------------------------
    by_qualname: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for row in cur.execute("SELECT id, name, qualname FROM symbols"):
        by_qualname[row[2]] = row[0]
        by_name.setdefault(row[1], []).append(row[0])

    def resolve(module_qual: str, scope: str, name: str) -> int | None:
        # Same-file first: innermost enclosing scope outward, then module level.
        parts = scope.split(".") if scope else []
        for i in range(len(parts), -1, -1):
            candidate = ".".join([module_qual, *parts[:i], name])
            if candidate in by_qualname:
                return by_qualname[candidate]
        if name in by_qualname:  # dotted module path (imports)
            return by_qualname[name]
        ids = by_name.get(name, [])
        return ids[0] if len(ids) == 1 else None  # unique global match only

    # -- pass 2: edges -------------------------------------------------------
    for file_id, module_qual, rel_dir, ex in extractions:
        for ref in ex.refs:
            src_qual = f"{module_qual}.{ref.scope}" if ref.scope else module_qual
            src_id = by_qualname.get(src_qual)
            dst_id = None
            if ref.kind == "imports" and ref.target_name.startswith("."):
                # Relative ES import ("./util"): resolve against the importing
                # file's directory, but only on an exact module-qualname hit —
                # anything fuzzier would be a guess, so it stays unresolved.
                candidate = posixpath.normpath(
                    posixpath.join(rel_dir, ref.target_name)
                ).replace("/", ".")
                dst_id = by_qualname.get(candidate)
            if dst_id is None:
                dst_id = resolve(module_qual, ref.scope, ref.target_name)
            if src_id is None or dst_id is None or src_id == dst_id:
                unresolved += 1
                continue
            cur.execute(
                "INSERT OR IGNORE INTO edges(src, dst, kind, line) VALUES (?, ?, ?, ?)",
                (src_id, dst_id, ref.kind, ref.line),
            )

    commit = _git_commit(root)
    for key, value in (
        ("root", str(root)),
        ("commit", commit or "no-git"),
        ("unresolved_refs", str(unresolved)),
    ):
        cur.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (key, value))
    conn.commit()

    counts = {
        "files": cur.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        "symbols": cur.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
        "edges": cur.execute("SELECT COUNT(*) FROM edges").fetchone()[0],
        "unresolved_refs": unresolved,
    }
    conn.close()
    return counts
