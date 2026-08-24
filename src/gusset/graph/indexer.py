"""Two-pass repo indexer.

Pass 1: extract every definition in every supported file, plus one package
node per external dependency declared in a manifest (pyproject.toml,
package.json, go.mod at the root or one level deep).
Pass 2: resolve references to definitions and write edges. Import refs that
miss internally get one exact shot at a declared package (see
_resolve_external) before counting as unresolved.

Resolution is receiver-aware and deliberately incomplete (no type inference —
see docs). Ambiguous or external references are never guessed into edges — a
wrong edge would poison the oracle — and every refusal is written to
`unresolved_refs`, not merely counted, so later queries can distinguish a
symbol nothing references from one whose references we could not see.
"""

from __future__ import annotations

import hashlib
import posixpath
import subprocess
from pathlib import Path

from gusset.graph.extract import LANGUAGE_BY_SUFFIX, Extraction, extract
from gusset.graph.manifest import norm_dist, parse_manifests
from gusset.graph.schema import connect

SKIP_DIRS = {
    ".git", ".hg", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox", ".eggs",
}

# Python import name -> distribution name, for the well-known cases where
# they differ. Exact table, never fuzzy — an unlisted mismatch stays
# unresolved rather than being guessed.
PY_IMPORT_TO_DIST = {
    "PIL": "pillow",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "tree_sitter_language_pack": "tree-sitter-language-pack",
    "tree_sitter": "tree-sitter",
    "langchain_core": "langchain-core",
    "langchain_anthropic": "langchain-anthropic",
    "pandaprobe_harness": "pandaprobe-harness",
}
# Namespace packages shared by many distributions (google-cloud-*, protobuf,
# ...): any single mapping would be a guess, so `import google` never maps.
PY_IMPORT_SKIP = {"google"}


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


class _PackageMaps:
    """Exact lookup tables from import names to package symbol ids."""

    def __init__(self) -> None:
        self.py_by_import: dict[str, int] = {}  # default import name -> id
        self.py_by_dist: dict[str, int] = {}    # normalized dist name -> id
        self.js_by_name: dict[str, int] = {}    # verbatim npm name -> id
        self.go_by_path: dict[str, int] = {}    # module path -> id


def _insert_packages(cur, root: Path) -> _PackageMaps:
    """One files row per manifest, one package symbol per declared dep.

    Dedup: first declaration wins per (ecosystem, name) — root manifests
    before subdirectories (parse_manifests order). A cross-ecosystem name
    collision on qualname keeps the first node only, and the loser maps to
    nothing: pointing its imports at another ecosystem's package would be
    a guess.
    """
    maps = _PackageMaps()
    file_ids: dict[str, int] = {}
    seen_qualnames: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for dep in parse_manifests(root, SKIP_DIRS):
        key = (dep.ecosystem, dep.name)
        qualname = f"pkg:{dep.name}"
        if key in seen or qualname in seen_qualnames:
            continue
        seen.add(key)
        seen_qualnames.add(qualname)
        if dep.source_file not in file_ids:
            source = (root / dep.source_file).read_bytes()
            cur.execute(
                "INSERT INTO files(path, language, sha) VALUES (?, 'manifest', ?)",
                (dep.source_file, hashlib.sha256(source).hexdigest()),
            )
            file_ids[dep.source_file] = cur.lastrowid
        cur.execute(
            "INSERT INTO symbols(file_id, name, qualname, kind, start_line, "
            "end_line, version) VALUES (?, ?, ?, 'package', 1, 1, ?)",
            (file_ids[dep.source_file], dep.name, qualname,
             dep.resolved_version or dep.version_spec),
        )
        pid = cur.lastrowid
        if dep.ecosystem == "python":
            maps.py_by_import[dep.name.lower().replace("-", "_")] = pid
            maps.py_by_dist[norm_dist(dep.name)] = pid
        elif dep.ecosystem == "js":
            maps.js_by_name[dep.name] = pid
        elif dep.ecosystem == "go":
            maps.go_by_path[dep.name] = pid
    return maps


def _resolve_external(language: str, target: str, maps: _PackageMaps) -> int | None:
    """Map an unresolved import to a declared package — exactly or not at all.

    python: first dotted segment, via the explicit mismatch table or the
    default rule (package name lowercased, "-" -> "_"). js: the verbatim
    bare specifier ("lodash/fp" is not "lodash" — no subpath stripping).
    go: the import path under the longest declared module path prefix.
    Relative specifiers and anything unmatched return None.
    """
    if language == "python":
        segment = target.split(".", 1)[0]
        if not segment or segment in PY_IMPORT_SKIP:
            return None
        dist = PY_IMPORT_TO_DIST.get(segment)
        if dist is not None:
            return maps.py_by_dist.get(norm_dist(dist))
        return maps.py_by_import.get(segment)
    if language in ("typescript", "tsx", "javascript"):
        if target.startswith((".", "/")):
            return None
        return maps.js_by_name.get(target)
    if language == "go":
        matches = [
            path for path in maps.go_by_path
            if target == path or target.startswith(path + "/")
        ]
        if not matches:
            return None
        return maps.go_by_path[max(matches, key=len)]
    return None


def index_repo(root: str | Path, db_path: str | Path) -> dict[str, int]:
    """Index `root` into `db_path`, replacing any prior index. Returns counts."""
    root = Path(root).resolve()
    conn = connect(db_path)
    cur = conn.cursor()
    for table in ("unresolved_refs", "edges", "symbols", "files", "meta"):
        cur.execute(f"DELETE FROM {table}")

    # (file_id, module_qual, rel_dir, language, ex)
    extractions: list[tuple[int, str, str, str, Extraction]] = []
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
        extractions.append((file_id, module_qual, rel.parent.as_posix(), language, ex))

    # -- pass 1b: package nodes from manifests --------------------------------
    packages = _insert_packages(cur, root)

    # -- resolution maps ----------------------------------------------------
    # Packages are excluded: internal resolution (calls, unique-name imports)
    # must never land on a dependency node — that path is reserved for the
    # exact external mapping below.
    by_qualname: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for row in cur.execute("SELECT id, name, qualname FROM symbols WHERE kind != 'package'"):
        by_qualname[row[2]] = row[0]
        by_name.setdefault(row[1], []).append(row[0])

    def resolve(module_qual: str, scope: str, name: str,
                receiver: str | None = None,
                import_aliases: dict[str, str] | None = None) -> int | None:
        """Resolve a reference to a symbol id, or None — never a guess.

        The receiver decides what evidence is available:

        * bare call `f()` — the name alone is the whole reference, so the
          same-file scope chain and then a UNIQUE repo-wide name are fair
          evidence.
        * `self.f()` — the enclosing class is known; resolve inside it only.
        * `x.f()` — the type of `x` is unknowable to a static parser. The only
          honest resolution is through an import alias in this file
          (`import lib` + `lib.f()` -> that module's `f`). Otherwise the
          reference stays UNRESOLVED. Guessing a unique global name here is
          what produced fabricated edges: `router.get()` in express and
          `store.get()` on a Map both resolved to an unrelated `CacheService.get`
          (found by pointing Gusset at a foreign TypeScript repo).
        """
        parts = scope.split(".") if scope else []

        if receiver == "self":
            # Innermost enclosing CLASS scope outward — never the whole repo.
            for i in range(len(parts), 0, -1):
                candidate = ".".join([module_qual, *parts[:i], name])
                if candidate in by_qualname:
                    return by_qualname[candidate]
            return None

        if receiver is not None:
            if receiver == "?" or not import_aliases:
                return None
            # Exact receiver match only — no prefix guessing. `a.b.f()` must
            # find the alias "a.b", not silently reuse the alias for "a".
            target = import_aliases.get(receiver)
            if target is None:
                return None
            return by_qualname.get(f"{target}.{name}")

        # Bare call: same-file scopes first, then a unique repo-wide name.
        for i in range(len(parts), -1, -1):
            candidate = ".".join([module_qual, *parts[:i], name])
            if candidate in by_qualname:
                return by_qualname[candidate]
        if name in by_qualname:  # dotted module path (imports)
            return by_qualname[name]
        ids = by_name.get(name, [])
        return ids[0] if len(ids) == 1 else None  # unique global match only

    # -- pass 2: edges -------------------------------------------------------
    for file_id, module_qual, rel_dir, language, ex in extractions:
        # Import aliases in THIS file, from the extractor: the only evidence
        # that makes a qualified call (`lib.f()`) resolvable without type
        # inference. Relative module paths are normalized to qualnames here.
        import_aliases: dict[str, str] = {}
        for bound, target in (ex.aliases or {}).items():
            module_part, _, member = target.partition("::")
            if module_part.startswith("."):
                module_part = posixpath.normpath(
                    posixpath.join(rel_dir, module_part)
                ).replace("/", ".")
            import_aliases[bound] = (
                f"{module_part}.{member}" if member else module_part)
        for ref in ex.refs:
            src_qual = f"{module_qual}.{ref.scope}" if ref.scope else module_qual
            src_id = by_qualname.get(src_qual)
            dst_id = None
            edge_kind = ref.kind
            if ref.kind == "imports" and ref.target_name.startswith("."):
                # Relative ES import ("./util"): resolve against the importing
                # file's directory, but only on an exact module-qualname hit —
                # anything fuzzier would be a guess, so it stays unresolved.
                candidate = posixpath.normpath(
                    posixpath.join(rel_dir, ref.target_name)
                ).replace("/", ".")
                dst_id = by_qualname.get(candidate)
            if dst_id is None:
                dst_id = resolve(module_qual, ref.scope, ref.target_name,
                                 receiver=getattr(ref, "receiver", None),
                                 import_aliases=import_aliases)
            if dst_id is None and ref.kind == "imports":
                # Internal miss: one exact shot at a declared dependency.
                dst_id = _resolve_external(language, ref.target_name, packages)
                if dst_id is not None:
                    edge_kind = "imports_external"
            if src_id is None or dst_id is None or src_id == dst_id:
                unresolved += 1
                cur.execute(
                    "INSERT INTO unresolved_refs(file_id, src_qualname, "
                    "target_name, receiver, kind, line, reason) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (file_id, src_qual, ref.target_name,
                     getattr(ref, "receiver", None), ref.kind, ref.line,
                     "scope" if src_id is None
                     else "target" if dst_id is None else "self_edge"),
                )
                continue
            cur.execute(
                "INSERT OR IGNORE INTO edges(src, dst, kind, line) VALUES (?, ?, ?, ?)",
                (src_id, dst_id, edge_kind, ref.line),
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
        "packages": cur.execute(
            "SELECT COUNT(*) FROM symbols WHERE kind = 'package'"
        ).fetchone()[0],
        "imports_external": cur.execute(
            "SELECT COUNT(*) FROM edges WHERE kind = 'imports_external'"
        ).fetchone()[0],
        "unresolved_refs": unresolved,
    }
    conn.close()
    return counts
