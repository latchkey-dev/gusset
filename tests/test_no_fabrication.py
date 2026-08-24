"""The never-guess invariant, pinned against the real pattern that broke it.

Found by pointing Gusset at a foreign TypeScript monorepo: `_callee_name`
discarded the receiver of `a.b.f()`, and the unique-global-name fallback then
linked express's `router.get()`, a `Map`'s `store.get()`, and supertest's
`request(app).get()` all to an unrelated `Vault.get`. 11 of 59 edges on
that repo were fabricated. A graph that invents edges cannot be an oracle, so
this test exists to make that failure loud forever.
"""

from pathlib import Path

from gusset.graph import GraphStore
from gusset.graph.indexer import index_repo

FIXTURE = Path(__file__).parent / "fixtures" / "fabrication"


def test_qualified_calls_are_not_guessed(tmp_path):
    db = tmp_path / "graph.db"
    counts = index_repo(FIXTURE, db)
    store = GraphStore(db)
    try:
        # The bait: a unique method name that any name-based fallback would grab.
        assert store.symbol_by_qualname("service.Vault.get") is not None
        for caller in ("routes", "routes.router"):
            assert not store.edge_exists(caller, "service.Vault.get", "calls")
        # No edge into Vault.get at all — nothing in routes.ts calls it.
        target = store.symbol_by_qualname("service.Vault.get")
        assert store.dependents(target.id) == []
        # And the misses are counted honestly rather than hidden.
        assert counts["unresolved_refs"] > 0
    finally:
        store.close()


def test_self_calls_still_resolve(tmp_path):
    """The fix must not cost `this.f()` / `self.f()` — the receiver IS known."""
    src = tmp_path / "selfcalls"
    src.mkdir()
    (src / "svc.py").write_text(
        "class Svc:\n"
        "    def outer(self):\n"
        "        return self.inner()\n"
        "    def inner(self):\n"
        "        return 1\n"
    )
    db = tmp_path / "self.db"
    index_repo(src, db)
    store = GraphStore(db)
    try:
        assert store.edge_exists("svc.Svc.outer", "svc.Svc.inner", "calls")
    finally:
        store.close()


def test_unresolved_refs_are_recorded_not_just_counted(tmp_path):
    """Refusing to guess is only honest if the refusal is kept.

    Counting unresolved references made the resolver's honesty read as a
    lie downstream: a symbol reachable only through a receiver we cannot
    type has no incoming edge, and "no incoming edge" was reported as dead
    code. Recording each refusal lets the query separate "nothing
    references this" from "we could not see the reference."
    """
    src = tmp_path / "recorded"
    src.mkdir()
    (src / "svc.py").write_text(
        "class Vault:\n"
        "    def stow(self):\n"          # only ever called via a local
        "        return 1\n"
        "    def orphan(self):\n"        # genuinely referenced by nothing
        "        return 2\n"
    )
    (src / "use.py").write_text(
        "def go(v):\n"
        "    return v.stow()\n"          # receiver type unknowable
    )
    db = tmp_path / "rec.db"
    counts = index_repo(src, db)
    store = GraphStore(db)
    try:
        assert counts["unresolved_refs"] > 0
        hits = store.unresolved_refs("stow")
        assert [h["receiver"] for h in hits] == ["v"]
        assert hits[0]["reason"] == "target"

        dead = {s.qualname for s in store.dead_symbols()}
        unverified = {s.qualname for s, _ in store.unverified_symbols()}
        # Unknowable, so withheld from the deletion list...
        assert "svc.Vault.stow" not in dead
        assert "svc.Vault.stow" in unverified
        # ...while a name nothing mentions at all stays actionable.
        assert "svc.Vault.orphan" in dead
    finally:
        store.close()
