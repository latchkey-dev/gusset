"""Package-manifest parsing: the external-dependency layer's input.

Parses manifests anywhere in the repo (monorepos keep them two or more
levels down): pyproject.toml, package.json, go.mod. Lockfiles beside a manifest
(uv.lock, package-lock.json) supply exact resolved versions when present.

Same design rule as the rest of the graph: never guess. A malformed
manifest yields zero deps (skipped, not invented); a dep without a
lockfile entry keeps resolved_version=None.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from gusset.graph.walk import walk_files

# PEP 508 requirement: leading distribution name, then optional extras,
# version spec, and ";" markers. Only the name and spec are kept.
_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")

# go.mod: `require path v1.2.3` (single) or lines inside `require ( ... )`.
_GO_REQUIRE = re.compile(r"^(\S+)\s+(v\S+)")


@dataclass
class PackageDep:
    name: str                     # verbatim from the manifest (extras stripped)
    version_spec: str | None      # declared constraint, verbatim
    resolved_version: str | None  # exact version from a lockfile, else None
    source_file: str              # repo-relative POSIX path of the manifest
    ecosystem: str                # python | js | go


def norm_dist(name: str) -> str:
    """PEP 503 normalization for python distribution names."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _parse_pep508(spec: str) -> tuple[str, str | None] | None:
    """"pandaprobe[langgraph]>=0.5.0" -> ("pandaprobe", ">=0.5.0")."""
    m = _PEP508_NAME.match(spec)
    if m is None:
        return None
    rest = spec[m.end():]
    if rest.startswith("["):  # strip extras
        close = rest.find("]")
        if close == -1:
            return None
        rest = rest[close + 1:]
    rest = rest.split(";", 1)[0].strip()  # drop environment markers
    return m.group(1), rest or None


def _uv_lock_versions(directory: Path) -> dict[str, str]:
    """Normalized dist name -> exact version from uv.lock, if present."""
    lock = directory / "uv.lock"
    if not lock.is_file():
        return {}
    try:
        data = tomllib.loads(lock.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for pkg in data.get("package", []):
        name, version = pkg.get("name"), pkg.get("version")
        if isinstance(name, str) and isinstance(version, str):
            out[norm_dist(name)] = version
    return out


def _npm_lock_versions(directory: Path) -> dict[str, str]:
    """Package name -> exact version from package-lock.json (v2/v3)."""
    lock = directory / "package-lock.json"
    if not lock.is_file():
        return {}
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for key, entry in data.get("packages", {}).items():
        # Keys are install paths: "" is the root project; direct deps are
        # "node_modules/<name>" (scoped: "node_modules/@scope/name").
        if not key.startswith("node_modules/") or not isinstance(entry, dict):
            continue
        name = key[len("node_modules/"):]
        if "/node_modules/" in name:
            continue  # nested (deduped transitive) copies — not the direct entry
        version = entry.get("version")
        if isinstance(version, str):
            out[name] = version
    return out


def _parse_pyproject(path: Path, rel: str) -> list[PackageDep]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return []
    project = data.get("project", {})
    if not isinstance(project, dict):
        return []
    specs: list[str] = []
    deps = project.get("dependencies", [])
    if isinstance(deps, list):
        specs.extend(s for s in deps if isinstance(s, str))
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in optional.values():
            if isinstance(group, list):
                specs.extend(s for s in group if isinstance(s, str))
    resolved = _uv_lock_versions(path.parent)
    out: list[PackageDep] = []
    for spec in specs:
        parsed = _parse_pep508(spec)
        if parsed is None:
            continue
        name, version_spec = parsed
        out.append(PackageDep(
            name=name,
            version_spec=version_spec,
            resolved_version=resolved.get(norm_dist(name)),
            source_file=rel,
            ecosystem="python",
        ))
    return out


def _parse_package_json(path: Path, rel: str) -> list[PackageDep]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    resolved = _npm_lock_versions(path.parent)
    out: list[PackageDep] = []
    for section in ("dependencies", "devDependencies"):
        entries = data.get(section, {})
        if not isinstance(entries, dict):
            continue
        for name, spec in entries.items():
            out.append(PackageDep(
                name=name,
                version_spec=spec if isinstance(spec, str) else None,
                resolved_version=resolved.get(name),
                source_file=rel,
                ecosystem="js",
            ))
    return out


def _parse_go_mod(path: Path, rel: str) -> list[PackageDep]:
    # go.mod versions are exact, so they double as the resolved version
    # (go.sum adds hashes, not different versions — resolution skipped).
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out: list[PackageDep] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if in_block:
            if stripped == ")":
                in_block = False
                continue
            m = _GO_REQUIRE.match(stripped)
            if m is not None:
                out.append(PackageDep(
                    name=m.group(1), version_spec=m.group(2),
                    resolved_version=m.group(2), source_file=rel, ecosystem="go",
                ))
            continue
        if stripped.startswith("require ("):
            in_block = True
            continue
        if stripped.startswith("require "):
            m = _GO_REQUIRE.match(stripped[len("require "):])
            if m is not None:
                out.append(PackageDep(
                    name=m.group(1), version_spec=m.group(2),
                    resolved_version=m.group(2), source_file=rel, ecosystem="go",
                ))
    return out


_PARSERS = {
    "pyproject.toml": _parse_pyproject,
    "package.json": _parse_package_json,
    "go.mod": _parse_go_mod,
}


def parse_manifests(
    root: str | Path, skip_dirs: frozenset[str] | set[str] = frozenset()
) -> list[PackageDep]:
    """All deps declared by manifests anywhere in the repo.

    Depth used to stop at one level, which is exactly one level short of
    where monorepos keep their manifests: a pnpm workspace declares its
    dependencies in `apps/api/package.json` and `packages/shared/
    package.json`. On the repo that exposed this, every one of the four
    workspace manifests was invisible, so `express`, `zod`, `next` and
    `@prisma/client` resolved to nothing despite being declared.

    Missing files are fine — returns whatever exists. Shallower manifests
    come first (root, then depth 1, ...), each depth in sorted order, so
    the indexer's "first declaration of a name per ecosystem wins" rule
    still prefers the root manifest's version.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    dirs = sorted(
        {p.parent for p in walk_files(root, set(skip_dirs)) if p.name in _PARSERS},
        key=lambda d: (len(d.relative_to(root).parts), d.as_posix()),
    )
    out: list[PackageDep] = []
    for directory in dirs:
        for filename, parser in _PARSERS.items():
            path = directory / filename
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                out.extend(parser(path, rel))
    return out
