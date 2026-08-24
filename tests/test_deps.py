"""External-dependency layer tests: manifests -> package nodes -> edges.

Fixture ground truth (tests/fixtures/pyproj):
  pyproject.toml declares requests>=2.31 and pyyaml>=6.0 (no lockfile)
  app imports requests (default name mapping) and yaml (explicit
  yaml -> pyyaml mapping), plus nonexistent_thing (undeclared: must
  stay unresolved — the graph never guesses).
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

from gusset.graph import GraphStore
from gusset.graph.indexer import index_repo
from gusset.graph.manifest import parse_manifests
from gusset.graph.schema import connect

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> GraphStore:
    db = tmp_path_factory.mktemp("db") / "graph.db"
    counts = index_repo(FIXTURE, db)
    assert counts["packages"] == 2
    assert counts["imports_external"] == 2
    s = GraphStore(db)
    yield s
    s.close()


# -- manifest parsing ---------------------------------------------------------


def test_parse_pyproject_fixture():
    deps = {d.name: d for d in parse_manifests(FIXTURE)}
    assert set(deps) == {"requests", "pyyaml"}
    assert deps["requests"].version_spec == ">=2.31"
    assert deps["requests"].resolved_version is None  # no uv.lock beside it
    assert deps["requests"].source_file == "pyproject.toml"
    assert deps["requests"].ecosystem == "python"


def test_parse_pyproject_extras_optional_and_lock(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0"\n'
        'dependencies = ["pandaprobe[langgraph]>=0.5.0"]\n'
        '[project.optional-dependencies]\nextra = ["rich>=15.0.0"]\n'
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "pandaprobe"\nversion = "0.5.2"\n'
        '[[package]]\nname = "rich"\nversion = "15.0.1"\n'
    )
    deps = {d.name: d for d in parse_manifests(tmp_path)}
    assert deps["pandaprobe"].version_spec == ">=0.5.0"  # extras stripped
    assert deps["pandaprobe"].resolved_version == "0.5.2"
    assert deps["rich"].resolved_version == "15.0.1"  # optional-dependencies


def test_parse_package_json_and_lock(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"lodash": "^4.17.0"},'
        ' "devDependencies": {"@types/node": "^20.0.0"}}'
    )
    (tmp_path / "package-lock.json").write_text(
        '{"lockfileVersion": 3, "packages": {'
        '"": {"name": "x"},'
        '"node_modules/lodash": {"version": "4.17.21"},'
        '"node_modules/@types/node": {"version": "20.1.0"}}}'
    )
    deps = {d.name: d for d in parse_manifests(tmp_path)}
    assert deps["lodash"].resolved_version == "4.17.21"
    assert deps["@types/node"].resolved_version == "20.1.0"
    assert deps["@types/node"].ecosystem == "js"


def test_parse_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\ngo 1.22\n\n"
        "require (\n"
        "\tgithub.com/stretchr/testify v1.9.0\n"
        "\tgolang.org/x/sync v0.7.0 // indirect\n"
        ")\n\n"
        "require github.com/pkg/errors v0.9.1\n"
    )
    deps = {d.name: d for d in parse_manifests(tmp_path)}
    assert set(deps) == {
        "github.com/stretchr/testify", "golang.org/x/sync", "github.com/pkg/errors"
    }
    # go.mod versions are exact — used directly as resolved (go.sum skipped).
    assert deps["github.com/pkg/errors"].resolved_version == "v0.9.1"


def test_parse_manifests_at_any_depth_and_malformed(tmp_path):
    """Monorepos keep manifests two levels down — `apps/api/package.json`.

    The scan used to stop at one level, which on a real pnpm workspace
    meant every workspace manifest was invisible and its declared deps
    (`express`, `zod`, `next`) resolved to nothing.
    """
    sub = tmp_path / "service"
    sub.mkdir()
    (sub / "package.json").write_text('{"dependencies": {"express": "^4"}}')
    deep = sub / "nested"
    deep.mkdir()
    (deep / "package.json").write_text('{"dependencies": {"koa": "^2"}}')
    vendored = tmp_path / "node_modules" / "left-pad"
    vendored.mkdir(parents=True)
    (vendored / "package.json").write_text('{"dependencies": {"never": "^1"}}')
    (tmp_path / "pyproject.toml").write_text("not [valid toml ((")

    deps = {d.name for d in parse_manifests(tmp_path, {"node_modules"})}
    assert deps == {"express", "koa"}
    # Vendored manifests are still skipped; a malformed one yields zero
    # deps rather than an exception or a guess.
    assert "never" not in deps


def test_shallower_manifests_come_first(tmp_path):
    """The indexer keeps the first declaration per name, so root wins."""
    (tmp_path / "package.json").write_text('{"dependencies": {"zod": "^3"}}')
    sub = tmp_path / "apps" / "api"
    sub.mkdir(parents=True)
    (sub / "package.json").write_text('{"dependencies": {"zod": "^1"}}')
    specs = [d.version_spec for d in parse_manifests(tmp_path) if d.name == "zod"]
    assert specs == ["^3", "^1"]


def test_parse_manifests_missing_root(tmp_path):
    assert parse_manifests(tmp_path / "does-not-exist") == []


# -- package nodes and edges --------------------------------------------------


def test_package_nodes_exist(store: GraphStore):
    pyyaml = store.symbol_by_qualname("pkg:pyyaml")
    assert pyyaml is not None and pyyaml.kind == "package"
    assert pyyaml.path == "pyproject.toml"
    assert pyyaml.version == ">=6.0"  # no lockfile: declared spec, verbatim
    requests = store.symbol_by_qualname("pkg:requests")
    assert requests is not None and requests.kind == "package"
    assert requests.version == ">=2.31"


def test_imports_external_edges(store: GraphStore):
    # `import requests` — default mapping (name == import name).
    assert store.edge_exists("app", "pkg:requests", "imports_external")
    # `import yaml` — explicit yaml -> pyyaml mapping.
    assert store.edge_exists("app", "pkg:pyyaml", "imports_external")


def test_undeclared_import_stays_unresolved(store: GraphStore):
    """`import nonexistent_thing` matches no declared package: no node,
    no edge — never fuzzy-matched into one."""
    assert store.symbol_by_qualname("pkg:nonexistent_thing") is None
    row = store.conn.execute(
        "SELECT COUNT(*) FROM edges e JOIN symbols s ON s.id = e.dst "
        "WHERE s.name = 'nonexistent_thing'"
    ).fetchone()
    assert row[0] == 0


def test_unresolved_refs_drop_with_manifest(tmp_path):
    """External resolution lowers the unresolved count — mechanically.

    Same fixture code without its pyproject.toml: requests/yaml/
    nonexistent_thing all miss (4 unresolved, incl. the pre-existing
    ambiguous `describe`). With the manifest, requests and yaml resolve
    to package nodes; only nonexistent_thing + describe remain (2).
    """
    stripped = tmp_path / "no-manifest"
    shutil.copytree(FIXTURE, stripped, ignore=shutil.ignore_patterns("pyproject.toml"))
    before = index_repo(stripped, tmp_path / "before.db")
    after = index_repo(FIXTURE, tmp_path / "after.db")
    assert before["unresolved_refs"] == 4
    assert after["unresolved_refs"] == 2
    assert before["packages"] == 0 and after["packages"] == 2
    assert before["imports_external"] == 0 and after["imports_external"] == 2


def test_js_bare_specifier_resolution(tmp_path):
    """JS: exact bare specifier only — subpaths are not the package."""
    (tmp_path / "package.json").write_text('{"dependencies": {"lodash": "^4"}}')
    (tmp_path / "app.js").write_text(
        'import _ from "lodash";\n'
        'import fp from "lodash/fp";\n'   # subpath: stays unresolved
        'import missing from "left-pad";\n'  # undeclared: stays unresolved
    )
    counts = index_repo(tmp_path, tmp_path / "g.db")
    store = GraphStore(tmp_path / "g.db")
    assert store.edge_exists("app", "pkg:lodash", "imports_external")
    assert counts["imports_external"] == 1
    assert counts["unresolved_refs"] == 2
    store.close()


def test_go_module_path_prefix_resolution(tmp_path):
    """Go: import paths resolve under the longest declared module path;
    stdlib ("fmt") matches nothing and stays unresolved."""
    (tmp_path / "go.mod").write_text(
        "module example.com/app\n\nrequire golang.org/x/sync v0.7.0\n"
    )
    (tmp_path / "main.go").write_text(
        'package main\n\nimport (\n\t"fmt"\n'
        '\t"golang.org/x/sync/errgroup"\n)\n\n'
        "func main() { fmt.Println(1); _ = errgroup.Group{} }\n"
    )
    counts = index_repo(tmp_path, tmp_path / "g.db")
    store = GraphStore(tmp_path / "g.db")
    assert store.edge_exists("main", "pkg:golang.org/x/sync", "imports_external")
    assert not store.edge_exists("main", "pkg:golang.org/x/sync", "imports")
    # "fmt" import + fmt.Println call stay unresolved, as before this layer.
    assert counts["unresolved_refs"] == 2
    store.close()


# -- store queries -------------------------------------------------------------


def test_packages_query(store: GraphStore):
    pkgs = store.packages()
    assert [(p.qualname, p.version) for p in pkgs] == [
        ("pkg:pyyaml", ">=6.0"),
        ("pkg:requests", ">=2.31"),
    ]


def test_package_dependents(store: GraphStore):
    pyyaml = store.symbol_by_qualname("pkg:pyyaml")
    dependents = {s.qualname for s in store.package_dependents(pyyaml.id)}
    assert dependents == {"app"}


def test_dead_symbols_exclude_packages(store: GraphStore):
    dead = {s.qualname for s in store.dead_symbols()}
    assert not any(q.startswith("pkg:") for q in dead)
    assert "pkg.lib.unused_fn" in dead  # real dead code still reported


def test_reverse_closure_from_package_seed(store: GraphStore):
    """Impact of bumping a dependency: the closure walks imports_external
    edges like any other edge kind."""
    pyyaml = store.symbol_by_qualname("pkg:pyyaml")
    closure = store.reverse_closure([pyyaml.id])
    quals = {store.conn.execute(
        "SELECT qualname FROM symbols WHERE id = ?", (sid,)
    ).fetchone()[0]: depth for sid, depth in closure.items()}
    assert quals["pkg:pyyaml"] == 0
    assert quals["app"] == 1


def test_module_views_stay_code_only(store: GraphStore):
    # Packages are not repo modules: no "pyproject" cluster, no external
    # edges in the atlas substrate.
    assert set(store.module_clusters()) == {"app", "pkg"}
    assert all(e["kind"] != "imports_external" for e in store.edge_listing())
    assert {(e["src"], e["dst"]) for e in store.cluster_edges()} == {("app", "pkg")}


def test_stats_report_external_layer(store: GraphStore):
    stats = store.stats()
    assert stats["packages"] == 2
    assert stats["imports_external"] == 2
    assert stats["symbols"]["package"] == 2
    assert stats["edges"]["imports_external"] == 2


def test_stats_zero_when_no_manifest(tmp_path):
    src = tmp_path / "repo"
    src.mkdir()
    (src / "solo.py").write_text("def f():\n    return 1\n")
    index_repo(src, tmp_path / "g.db")
    stats = GraphStore(tmp_path / "g.db").stats()
    assert stats["packages"] == 0 and stats["imports_external"] == 0


# -- schema migration -----------------------------------------------------------


def test_connect_adds_version_column_to_old_db(tmp_path):
    """Databases created before the external-dependency layer lack
    symbols.version; connect() must add it in place."""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,"
        " language TEXT NOT NULL, sha TEXT NOT NULL);"
        "CREATE TABLE symbols (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL,"
        " name TEXT NOT NULL, qualname TEXT NOT NULL, kind TEXT NOT NULL,"
        " start_line INTEGER NOT NULL, end_line INTEGER NOT NULL);"
    )
    conn.close()
    conn = connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(symbols)")}
    assert "version" in cols
    conn.close()
