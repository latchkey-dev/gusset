"""Graph substrate tests against the known fixture repo.

The fixture's ground truth:
  app.main        calls  pkg.lib.helper, instantiates pkg.models.Child
  pkg.lib.helper  calls  pkg.lib._internal
  pkg.models.Child inherits pkg.models.Base
  pkg.lib.unused_fn has no callers (dead)
  app             imports requests + yaml (declared in pyproject.toml)
                  and nonexistent_thing (undeclared — stays unresolved)
"""

from pathlib import Path

import pytest

from gusset.graph import GraphStore
from gusset.graph.indexer import index_repo

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> GraphStore:
    db = tmp_path_factory.mktemp("db") / "graph.db"
    counts = index_repo(FIXTURE, db)
    # 4 python files + pyproject.toml (indexed as a manifest files row).
    assert counts["files"] == 5
    s = GraphStore(db)
    yield s
    s.close()


def test_symbols_extracted(store: GraphStore):
    helper = store.symbol_by_qualname("pkg.lib.helper")
    assert helper is not None and helper.kind == "function"
    child = store.symbol_by_qualname("pkg.models.Child")
    assert child is not None and child.kind == "class"
    describe = store.symbol_by_qualname("pkg.models.Child.describe")
    assert describe is not None and describe.kind == "method"
    assert store.symbol_by_qualname("app.main") is not None


def test_call_edges(store: GraphStore):
    assert store.edge_exists("app.main", "pkg.lib.helper", "calls")
    assert store.edge_exists("pkg.lib.helper", "pkg.lib._internal", "calls")


def test_inheritance_edge(store: GraphStore):
    assert store.edge_exists("pkg.models.Child", "pkg.models.Base", "inherits")


def test_import_edges(store: GraphStore):
    assert store.edge_exists("app", "pkg.models", "imports")


def test_no_fabricated_edges(store: GraphStore):
    """The oracle must never contain edges that aren't in the code."""
    assert not store.edge_exists("app.main", "pkg.lib.unused_fn")
    assert not store.edge_exists("pkg.lib.helper", "app.main", "calls")


def test_reverse_closure_is_impact_ground_truth(store: GraphStore):
    internal = store.symbol_by_qualname("pkg.lib._internal")
    closure = store.reverse_closure([internal.id])
    quals = {store.conn.execute(
        "SELECT qualname FROM symbols WHERE id = ?", (sid,)
    ).fetchone()[0]: depth for sid, depth in closure.items()}
    # Changing _internal impacts helper (depth 1) which impacts main (depth 2).
    assert quals["pkg.lib._internal"] == 0
    assert quals["pkg.lib.helper"] == 1
    assert quals["app.main"] == 2
    assert "pkg.lib.unused_fn" not in quals


def test_dead_symbols(store: GraphStore):
    dead = {s.qualname for s in store.dead_symbols()}
    assert "pkg.lib.unused_fn" in dead
    assert "pkg.lib.helper" not in dead
    assert "pkg.lib._internal" not in dead


def test_dependents_and_dependencies(store: GraphStore):
    helper = store.symbol_by_qualname("pkg.lib.helper")
    dependent_quals = {s.qualname for s in store.dependents(helper.id)}
    assert "app.main" in dependent_quals
    dep_quals = {s.qualname for s in store.dependencies(helper.id)}
    assert "pkg.lib._internal" in dep_quals


def test_search(store: GraphStore):
    hits = {s.qualname for s in store.search("helper")}
    assert "pkg.lib.helper" in hits


def test_symbols_by_qualname_suffix(store: GraphStore):
    assert {s.qualname for s in store.symbols_by_qualname_suffix("lib.helper")} == {
        "pkg.lib.helper"
    }
    # Exact qualname resolves too.
    assert {s.qualname for s in store.symbols_by_qualname_suffix("pkg.lib.helper")} == {
        "pkg.lib.helper"
    }
    # Underscore is literal, not a wildcard (LIKE would treat it as one).
    assert store.symbols_by_qualname_suffix("lib._internal")
    assert not store.symbols_by_qualname_suffix("lib.internal")
    # Case-sensitive (LIKE is ASCII case-insensitive).
    assert not store.symbols_by_qualname_suffix("LIB.HELPER")
    # Suffix matches only at a dot boundary.
    assert not store.symbols_by_qualname_suffix("b.helper")
    assert not store.symbols_by_qualname_suffix("nope.helper")


def test_module_clusters_partition(store: GraphStore):
    clusters = store.module_clusters()
    assert set(clusters) == {"app", "pkg"}
    assert "app.main" in {s.qualname for s in clusters["app"]}
    pkg_quals = {s.qualname for s in clusters["pkg"]}
    assert {"pkg.lib.helper", "pkg.lib._internal", "pkg.models.Child"} <= pkg_quals


def test_edge_listing_matches_edge_exists(store: GraphStore):
    listing = store.edge_listing()
    assert listing, "fixture graph has edges"
    for e in listing:
        assert store.edge_exists(e["src_qualname"], e["dst_qualname"], e["kind"])
    triples = {(e["src_qualname"], e["dst_qualname"], e["kind"]) for e in listing}
    assert ("pkg.lib.helper", "pkg.lib._internal", "calls") in triples


def test_cluster_edges_are_inter_module_only(store: GraphStore):
    edges = {(e["src"], e["dst"]): e for e in store.cluster_edges()}
    assert ("app", "pkg") in edges
    kinds = edges[("app", "pkg")]["kinds"]
    assert "calls" in kinds and "imports" in kinds
    assert ("pkg", "app") not in edges  # no fabricated/reverse cluster edges
    assert all(src != dst for src, dst in edges)


def test_stats(store: GraphStore):
    stats = store.stats()
    # 4 python files + pyproject.toml (manifest files row).
    assert stats["files"] == 5
    assert stats["symbols"]["class"] == 2
    assert stats["edges"]["calls"] >= 2
    assert stats["meta"]["commit"]  # always recorded, "no-git" if absent
