"""Graph substrate tests against the known TypeScript fixture repo.

The fixture's ground truth:
  app.main       calls  util.helper, app.fmt (top-level arrow fn),
                 instantiates shapes.Fancy, calls shapes.Fancy.describe
  util.helper    calls  util.double
  shapes.Fancy   inherits shapes.Base
  util.unusedExport has no callers (dead)
"""

from pathlib import Path

import pytest

from gusset.graph import GraphStore
from gusset.graph.extract import extract
from gusset.graph.indexer import index_repo

FIXTURE = Path(__file__).parent / "fixtures" / "tsproj"


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> GraphStore:
    db = tmp_path_factory.mktemp("db") / "graph.db"
    counts = index_repo(FIXTURE, db)
    assert counts["files"] == 3
    # Every ref in the fixture resolves: relative imports, calls, inherits.
    assert counts["unresolved_refs"] == 0
    s = GraphStore(db)
    yield s
    s.close()


def test_symbols_extracted(store: GraphStore):
    helper = store.symbol_by_qualname("util.helper")
    assert helper is not None and helper.kind == "function"
    fmt = store.symbol_by_qualname("app.fmt")  # arrow fn assigned to const
    assert fmt is not None and fmt.kind == "function"
    fancy = store.symbol_by_qualname("shapes.Fancy")
    assert fancy is not None and fancy.kind == "class"
    describe = store.symbol_by_qualname("shapes.Fancy.describe")
    assert describe is not None and describe.kind == "method"
    assert store.symbol_by_qualname("app.main") is not None


def test_call_edges(store: GraphStore):
    assert store.edge_exists("app.main", "util.helper", "calls")
    assert store.edge_exists("app.main", "app.fmt", "calls")
    assert store.edge_exists("app.main", "shapes.Fancy", "calls")  # new Fancy()
    assert store.edge_exists("app.main", "shapes.Fancy.describe", "calls")
    assert store.edge_exists("util.helper", "util.double", "calls")


def test_inheritance_edge(store: GraphStore):
    assert store.edge_exists("shapes.Fancy", "shapes.Base", "inherits")


def test_import_edges(store: GraphStore):
    # Relative ES imports resolve to in-repo module symbols.
    assert store.edge_exists("app", "util", "imports")
    assert store.edge_exists("app", "shapes", "imports")


def test_no_fabricated_edges(store: GraphStore):
    """The oracle must never contain edges that aren't in the code."""
    assert not store.edge_exists("app.main", "util.unusedExport")
    assert not store.edge_exists("util.helper", "app.main", "calls")


def test_reverse_closure_is_impact_ground_truth(store: GraphStore):
    double = store.symbol_by_qualname("util.double")
    closure = store.reverse_closure([double.id])
    quals = {store.conn.execute(
        "SELECT qualname FROM symbols WHERE id = ?", (sid,)
    ).fetchone()[0]: depth for sid, depth in closure.items()}
    # Changing double impacts helper (depth 1) which impacts main (depth 2).
    assert quals["util.double"] == 0
    assert quals["util.helper"] == 1
    assert quals["app.main"] == 2
    assert "util.unusedExport" not in quals


def test_dead_symbols(store: GraphStore):
    dead = {s.qualname for s in store.dead_symbols()}
    assert "util.unusedExport" in dead
    assert "util.helper" not in dead
    assert "util.double" not in dead
    assert "app.fmt" not in dead


def test_js_and_tsx_grammar_variants():
    # JS puts the extends expression directly under class_heritage (no
    # extends_clause wrapper) — pin the one structural divergence from TS.
    ex = extract(b"class Kid extends ns.Base { go() { return 1; } }", "javascript")
    assert [(r.target_name, r.kind) for r in ex.refs] == [("Base", "inherits")]
    kinds = {d.qualname: d.kind for d in ex.defs}
    assert kinds == {"Kid": "class", "Kid.go": "method"}
    # The tsx grammar handles plain TS constructs too.
    ex = extract(b"const f = (x: number): number => g(x);\n", "tsx")
    assert [(d.qualname, d.kind) for d in ex.defs] == [("f", "function")]
    assert [(r.scope, r.target_name, r.kind) for r in ex.refs] == [("f", "g", "calls")]
