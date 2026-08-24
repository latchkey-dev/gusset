"""TypeScript module resolution, from declarations that exist in the repo.

A TS monorepo writes imports in forms a filesystem walk cannot follow:

    import { api }  from "@/lib/api"              tsconfig paths alias
    import { Svc }  from "@pulse/shared"          workspace package
    import { r }    from "./routes/incidents.js"  NodeNext: .js means .ts

None of these are ambiguous. Each is answered by a file already in the
repo — a tsconfig's `paths`, a package.json's `name` and `main`, or the
TS compiler's documented rule that a `.js` specifier in TS source refers
to the `.ts` that produces it. So resolving them reads declarations; it
does not guess, and an unmatched specifier still resolves to nothing.

The output is a list of candidate module qualnames in priority order. The
indexer takes the first that exists in the graph, so a candidate for a
file that isn't there costs nothing.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from gusset.graph.walk import walk_files

# Extensions a specifier may carry. A `.js` specifier in TS source names
# the file that will be emitted; the source is the `.ts`, so the extension
# is stripped and the module qualname is matched against what we indexed.
_SPEC_EXTS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas, respecting strings.

    tsconfig.json is JSONC by convention and `json.loads` rejects it. Doing
    this with a scanner rather than a regex keeps `"https://x"` intact.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    # Trailing commas: ",}" / ",]" with any whitespace between.
    result: list[str] = []
    for idx, ch in enumerate(cleaned):
        if ch == ",":
            rest = cleaned[idx + 1:].lstrip()
            if rest[:1] in ("}", "]"):
                continue
        result.append(ch)
    return "".join(result)


def _load_jsonc(path: Path) -> dict:
    try:
        return json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # A config we cannot parse resolves nothing, which is the same
        # outcome as before it existed. Never a crash on someone's repo.
        return {}


@dataclass
class TsProject:
    """Alias and workspace declarations found in the repo."""

    # (config_dir_rel, alias_prefix, [target_prefixes]) — '*' already stripped.
    aliases: list[tuple[str, str, list[str]]] = field(default_factory=list)
    # package name -> repo-relative entry path, extension stripped
    packages: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.aliases or self.packages)


def _resolve_extends(config: dict, config_path: Path, root: Path,
                     depth: int = 0) -> dict:
    """Merge `extends` parents; child keys win. Depth-capped against cycles."""
    parent_ref = config.get("extends")
    if not isinstance(parent_ref, str) or depth > 8:
        return config
    if not parent_ref.startswith("."):
        return config          # a package-name preset we cannot read: ignore
    parent_path = (config_path.parent / parent_ref).resolve()
    if parent_path.suffix != ".json":
        parent_path = parent_path.with_suffix(".json")
    if not parent_path.is_file() or root not in parent_path.parents:
        return config
    parent = _resolve_extends(_load_jsonc(parent_path), parent_path, root, depth + 1)
    merged = {**parent, **config}
    merged["compilerOptions"] = {
        **parent.get("compilerOptions", {}),
        **config.get("compilerOptions", {}),
    }
    return merged


def collect(root: Path, skip_dirs: set[str]) -> TsProject:
    """Scan the repo for tsconfig `paths` and workspace package names."""
    project = TsProject()
    for path in walk_files(root, skip_dirs):
        name = path.name
        if path.suffix != ".json":
            continue
        if name != "package.json" and not name.startswith("tsconfig"):
            continue
        rel = path.relative_to(root)
        data = _load_jsonc(path)
        if not data:
            continue
        config_dir = rel.parent.as_posix()
        config_dir = "" if config_dir == "." else config_dir

        if name == "package.json":
            pkg_name = data.get("name")
            entry = data.get("types") or data.get("main")
            if isinstance(pkg_name, str) and pkg_name:
                if not isinstance(entry, str) or not entry:
                    entry = "index"
                entry_path = posixpath.normpath(
                    posixpath.join(config_dir, entry)) if config_dir else entry
                entry_path = posixpath.normpath(entry_path)
                for ext in _SPEC_EXTS:
                    if entry_path.endswith(ext):
                        entry_path = entry_path[: -len(ext)]
                        break
                project.packages.setdefault(pkg_name, entry_path)
            continue

        merged = _resolve_extends(data, path, root)
        paths = merged.get("compilerOptions", {}).get("paths")
        base_url = merged.get("compilerOptions", {}).get("baseUrl")
        if not isinstance(paths, dict):
            continue
        base = config_dir
        if isinstance(base_url, str) and base_url not in (".", "./"):
            base = posixpath.normpath(posixpath.join(config_dir, base_url))
            base = "" if base == "." else base
        for pattern, targets in paths.items():
            if not isinstance(pattern, str) or not isinstance(targets, list):
                continue
            prefix = pattern[:-1] if pattern.endswith("*") else pattern
            resolved: list[str] = []
            for target in targets:
                if not isinstance(target, str):
                    continue
                target_prefix = target[:-1] if target.endswith("*") else target
                joined = posixpath.normpath(
                    posixpath.join(base, target_prefix)) if base else target_prefix
                joined = posixpath.normpath(joined)
                resolved.append("" if joined == "." else joined)
            if resolved:
                project.aliases.append((config_dir, prefix, resolved))
    # Longest alias prefix first, and deeper configs before shallower ones,
    # so the most specific declaration wins.
    project.aliases.sort(key=lambda a: (-len(a[0]), -len(a[1])))
    return project


def _strip_ext(path: str) -> str:
    for ext in _SPEC_EXTS:
        if path.endswith(ext):
            return path[: -len(ext)]
    return path


def _module_candidates(repo_path: str) -> list[str]:
    """A repo-relative path -> candidate module qualnames, best first."""
    stem = _strip_ext(posixpath.normpath(repo_path)).strip("/")
    if not stem or stem.startswith(".."):
        return []
    dotted = stem.replace("/", ".")
    # `./routes` may mean `routes/index.ts`, the directory-entry convention.
    return [dotted, f"{dotted}.index"]


def candidates(project: TsProject, importer_dir: str, specifier: str) -> list[str]:
    """Candidate module qualnames for `specifier` imported from `importer_dir`.

    Relative specifiers are resolved against the importing file's directory;
    aliased and workspace specifiers against the declaration that defines
    them. A specifier matching nothing yields no candidates — never a
    fallback guess.
    """
    if not specifier:
        return []

    if specifier.startswith("."):
        joined = posixpath.join(importer_dir, specifier) if importer_dir else specifier
        return _module_candidates(joined)

    out: list[str] = []
    for config_dir, prefix, targets in project.aliases:
        # An alias only applies inside the project that declares it.
        if config_dir and not (
            importer_dir == config_dir or importer_dir.startswith(config_dir + "/")
        ):
            continue
        if not specifier.startswith(prefix):
            continue
        rest = specifier[len(prefix):]
        for target in targets:
            out.extend(_module_candidates(posixpath.join(target, rest)))
        if out:
            return out

    # Workspace package: exact name, or name + subpath.
    entry = project.packages.get(specifier)
    if entry is not None:
        return _module_candidates(entry)
    for pkg_name, pkg_entry in project.packages.items():
        if specifier.startswith(pkg_name + "/"):
            sub = specifier[len(pkg_name) + 1:]
            pkg_dir = posixpath.dirname(pkg_entry)
            out.extend(_module_candidates(posixpath.join(pkg_dir, sub)))
            if out:
                return out
    return out
