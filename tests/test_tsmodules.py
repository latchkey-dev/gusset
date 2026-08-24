"""TypeScript module resolution across a workspace monorepo.

A foreign pnpm monorepo produced 2 import edges for a repo where every
file begins with imports. The specifiers were not ambiguous — they were
answered by a tsconfig, a package.json, and the compiler's own
`.js`-means-`.ts` rule, none of which were being read.
"""

from pathlib import Path

import pytest

from gusset.graph import GraphStore, tsmodules
from gusset.graph.indexer import SKIP_DIRS, index_repo

FIXTURE = Path(__file__).parent / "fixtures" / "tsmono"


@pytest.fixture()
def store(tmp_path) -> GraphStore:
    db = tmp_path / "graph.db"
    index_repo(FIXTURE, db)
    s = GraphStore(db)
    yield s
    s.close()


def test_nodenext_js_specifier_resolves_to_source(store: GraphStore):
    """`./routes/health.js` in TS source names the .ts that emits it."""
    assert store.edge_exists(
        "apps.api.src.index", "apps.api.src.routes.health", "imports")


def test_tsconfig_path_alias_resolves(store: GraphStore):
    assert store.edge_exists(
        "apps.web.src.app.page", "apps.web.src.lib.api", "imports")


def test_workspace_package_resolves(store: GraphStore):
    """`@demo/shared` is declared by a package.json in the repo."""
    assert store.edge_exists(
        "apps.web.src.app.page", "packages.shared.src.index", "imports")


def test_cross_package_calls_resolve(store: GraphStore):
    assert store.edge_exists(
        "apps.web.src.app.page.Page", "packages.shared.src.index.makeStatus",
        "calls")


def test_nothing_is_left_unresolved(tmp_path):
    """This fixture is fully internal; every reference should land."""
    counts = index_repo(FIXTURE, tmp_path / "g.db")
    assert counts["unresolved_refs"] == 0


def test_alias_does_not_leak_across_projects():
    """`@/*` declared by apps/web must not apply to apps/api.

    Two projects in one repo routinely bind the same alias to different
    directories. Applying a project's alias outside it would invent edges
    between packages that never import each other.
    """
    project = tsmodules.collect(FIXTURE, SKIP_DIRS)
    assert tsmodules.candidates(project, "apps/web/src/app", "@/lib/api")
    assert tsmodules.candidates(project, "apps/api/src", "@/lib/api") == []


def test_unknown_specifier_resolves_to_nothing():
    project = tsmodules.collect(FIXTURE, SKIP_DIRS)
    assert tsmodules.candidates(project, "apps/web/src", "express") == []
    assert tsmodules.candidates(project, "apps/web/src", "@nope/missing") == []


def test_jsonc_comments_are_stripped_without_eating_strings():
    """tsconfig is JSONC. A `//` inside a string is not a comment."""
    text = """
    {
      // leading comment
      "url": "https://example.com/x", /* trailing */
      "list": [1, 2,],
    }
    """
    import json
    parsed = json.loads(tsmodules._strip_jsonc(text))
    assert parsed["url"] == "https://example.com/x"
    assert parsed["list"] == [1, 2]
