"""JSX usage, default exports, and constructors — found on a foreign React repo.

Every assertion here corresponds to a symbol that a real Next.js/React
codebase reported as dead code while being rendered on every screen. The
graph was not wrong about the edges it had; it was missing the three ways
React code actually references things.
"""

from pathlib import Path

import pytest

from gusset.graph import GraphStore
from gusset.graph.extract import extract
from gusset.graph.indexer import index_repo

FIXTURE = Path(__file__).parent / "fixtures" / "tsxapp"


@pytest.fixture()
def store(tmp_path) -> GraphStore:
    db = tmp_path / "graph.db"
    index_repo(FIXTURE, db)
    s = GraphStore(db)
    yield s
    s.close()


def test_jsx_element_is_a_reference(store: GraphStore):
    """`<Panel />` uses Panel exactly as `Panel()` would."""
    assert store.edge_exists("page.HomePage", "panel.Panel", "calls")
    assert store.edge_exists("panel.Panel", "badge.StatusBadge", "calls")


def test_intrinsic_elements_are_not_symbols():
    """`<div>` is the DOM, not a symbol in the repo.

    JSX compiles lowercase tags to strings and capitalized ones to
    identifiers, so capitalization is the language's own rule here, not a
    heuristic of ours.
    """
    ex = extract(b"function C(){ return <div><span/><Thing/></div>; }", "tsx")
    targets = [r.target_name for r in ex.refs if r.kind == "calls"]
    assert targets == ["Thing"]


def test_closing_tag_does_not_double_count():
    ex = extract(b"function C(){ return <Panel>hi</Panel>; }", "tsx")
    assert [r.target_name for r in ex.refs if r.kind == "calls"] == ["Panel"]


def test_default_export_is_an_edge(store: GraphStore):
    """A page component is referenced by the framework, not by the repo.

    Without this edge every Next.js page and every default-exported
    component is unreferenced and reads as deletable.
    """
    assert store.edge_exists("page", "page.HomePage", "exports")
    dead = {s.qualname for s in store.dead_symbols()}
    assert "page.HomePage" not in dead


def test_anonymous_default_export_records_nothing():
    """`export default () => 1` names no symbol, so nothing is attributed."""
    ex = extract(b"export default () => 1;", "tsx")
    assert [r for r in ex.refs if r.kind == "exports"] == []


def test_constructor_is_not_dead_code(store: GraphStore):
    """`constructor` is TypeScript's `__init__`: invoked, never by name.

    Python's dunder rule already excluded `__init__`; the TS equivalent was
    missing, so every class with a constructor carried a phantom dead
    symbol.
    """
    dead = {s.qualname for s in store.dead_symbols()}
    assert "page.Client.constructor" not in dead
    assert store.symbol_by_qualname("page.Client.constructor") is not None
