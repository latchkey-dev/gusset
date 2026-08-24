"""Graph substrate tests against the known Go fixture repo (one package).

The fixture's ground truth:
  app.main               calls  fmt.Println (external), greeter.report;
                         `g.Greet()` / `g.Rename()` are NOT edges — `g` is a
                         local whose type only a type checker could know,
                                app.report, fmt.Println (stdlib, unresolved)
  greeter.Greeter.Greet  calls  greeter.decorate
  greeter.Unused         has no callers (dead)
"""

from pathlib import Path

import pytest

from gusset.graph import GraphStore
from gusset.graph.extract import extract
from gusset.graph.indexer import index_repo

FIXTURE = Path(__file__).parent / "fixtures" / "goproj"


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> GraphStore:
    db = tmp_path_factory.mktemp("db") / "graph.db"
    counts = index_repo(FIXTURE, db)
    assert counts["files"] == 2
    # Exactly two stdlib refs stay unresolved: import "fmt" and fmt.Println.
    # Counted, never guessed into edges.
    # 2 pre-existing (fmt.Println, the fmt import) + `g.Greet()` and
    # `g.Rename()`: unknown receiver type, so no edge is invented.
    assert counts["unresolved_refs"] == 4
    s = GraphStore(db)
    yield s
    s.close()


def test_symbols_extracted(store: GraphStore):
    greeter = store.symbol_by_qualname("greeter.Greeter")
    assert greeter is not None and greeter.kind == "class"  # struct
    speaker = store.symbol_by_qualname("greeter.Speaker")
    assert speaker is not None and speaker.kind == "class"  # interface
    greet = store.symbol_by_qualname("greeter.Greeter.Greet")
    assert greet is not None and greet.kind == "method"
    rename = store.symbol_by_qualname("greeter.Greeter.Rename")
    assert rename is not None and rename.kind == "method"  # pointer receiver
    decorate = store.symbol_by_qualname("greeter.decorate")
    assert decorate is not None and decorate.kind == "function"
    assert store.symbol_by_qualname("app.main") is not None


def test_call_edges(store: GraphStore):
    # No edge for `g.Greet()` / `g.Rename()`: the receiver is a local variable,
    # and inventing the edge is what fabricated `router.get()` -> CacheService
    # on a real repo. Recovering these honestly needs local type tracking.
    assert not store.edge_exists("app.main", "greeter.Greeter.Greet", "calls")
    assert not store.edge_exists("app.main", "greeter.Greeter.Rename", "calls")
    assert store.edge_exists("app.main", "app.report", "calls")
    assert store.edge_exists("greeter.Greeter.Greet", "greeter.decorate", "calls")


def test_no_fabricated_edges(store: GraphStore):
    """The oracle must never contain edges that aren't in the code."""
    assert not store.edge_exists("app.main", "greeter.Unused")
    assert not store.edge_exists("greeter.decorate", "app.main", "calls")
    # Same package, no in-repo import — must not be invented from "fmt".
    assert not store.edge_exists("app", "greeter", "imports")


def test_reverse_closure_is_impact_ground_truth(store: GraphStore):
    decorate = store.symbol_by_qualname("greeter.decorate")
    closure = store.reverse_closure([decorate.id])
    quals = {store.conn.execute(
        "SELECT qualname FROM symbols WHERE id = ?", (sid,)
    ).fetchone()[0]: depth for sid, depth in closure.items()}
    # Changing decorate impacts Greet (depth 1). The chain stops there: the
    # main -> Greet hop went through `g.Greet()`, an unknowable receiver.
    assert quals["greeter.decorate"] == 0
    assert quals["greeter.Greeter.Greet"] == 1
    assert "app.main" not in quals
    assert "greeter.Unused" not in quals


def test_dead_symbols(store: GraphStore):
    dead = {s.qualname for s in store.dead_symbols()}
    assert "greeter.Unused" in dead
    assert "greeter.decorate" not in dead
    assert "app.report" not in dead

    # `g.Greet()` is a call through a local variable, whose type a parser
    # cannot know — so the resolver refuses it and the graph holds no edge.
    # That is not evidence of death, and reporting it as dead code is how
    # a correct refusal turns into a wrong answer. It belongs in the
    # middle bucket, attributed to the references we could not resolve.
    assert "greeter.Greeter.Greet" not in dead
    unverified = {s.qualname: hits for s, hits in store.unverified_symbols()}
    assert unverified["greeter.Greeter.Greet"] > 0


def test_grouped_import_form():
    # The fixture uses the single form (import_spec directly under the
    # declaration); pin the grouped form (import_spec_list wrapper) too.
    ex = extract(b'package p\n\nimport (\n\t"fmt"\n\t"strings"\n)\n', "go")
    assert [(r.target_name, r.kind) for r in ex.refs] == [
        ("fmt", "imports"),
        ("strings", "imports"),
    ]
