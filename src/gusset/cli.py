"""Gusset command-line interface.

Commands land phase by phase:
  index / stats / deadcode  — phase 1 (graph substrate, no LLM)
  impact                    — phase 2
  atlas / docs-drift        — phase 5
  watch / init              — phase 6 (autonomous mode)
"""

import json
from pathlib import Path

import typer

from gusset import __version__

app = typer.Typer(
    name="gusset",
    help="An autonomous repo custodian, engineered as graphs.",
    no_args_is_help=True,
)

DEFAULT_DB = Path(".gusset/graph.db")


def _db_path(db: Path | None) -> Path:
    path = db or DEFAULT_DB
    if not path.exists():
        typer.echo(f"No graph at {path} — run `gusset index <repo>` first.", err=True)
        raise typer.Exit(1)
    return path


@app.callback()
def main() -> None:
    """An autonomous repo custodian, engineered as graphs."""


@app.command()
def version() -> None:
    """Print the Gusset version."""
    typer.echo(f"gusset {__version__}")


@app.command()
def index(
    repo: Path = typer.Argument(..., exists=True, file_okay=False, help="Repo root to index."),
    db: Path = typer.Option(DEFAULT_DB, help="Where to write the graph database."),
) -> None:
    """Build the code knowledge graph for a repository."""
    from gusset.graph.indexer import index_repo

    db.parent.mkdir(parents=True, exist_ok=True)
    counts = index_repo(repo, db)
    typer.echo(json.dumps({"db": str(db), **counts}))


@app.command()
def stats(db: Path = typer.Option(DEFAULT_DB, help="Graph database path.")) -> None:
    """Show graph statistics: files, symbols, edges, index metadata."""
    from gusset.graph import GraphStore

    store = GraphStore(_db_path(db))
    typer.echo(json.dumps(store.stats(), indent=2))
    store.close()


@app.command()
def deadcode(db: Path = typer.Option(DEFAULT_DB, help="Graph database path.")) -> None:
    """List symbols with no incoming edges — deletion candidates.

    Pure graph query: no LLM involved, nothing to distrust.
    """
    from gusset.graph import GraphStore

    store = GraphStore(_db_path(db))
    dead = [
        {"qualname": s.qualname, "path": s.path, "line": s.start_line, "kind": s.kind}
        for s in store.dead_symbols()
    ]
    typer.echo(json.dumps(dead, indent=2))
    store.close()
