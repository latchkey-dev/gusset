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
def impact(
    symbol: list[str] = typer.Option([], "--symbol", help="Seed symbol qualname(s), e.g. pkg.lib.helper."),
    diff: str | None = typer.Option(None, "--diff", help="Git range, e.g. HEAD~1; seeds from changed lines."),
    repo: Path = typer.Option(Path("."), help="Repo root (for --diff)."),
    db: Path = typer.Option(DEFAULT_DB, help="Graph database path."),
    out: Path = typer.Option(Path("impact-report.md"), help="Where to write the report."),
    yes: bool = typer.Option(False, "--yes", help="Waive the human gate (autonomous mode)."),
    model_name: str = typer.Option("claude-opus-5", "--model", envvar="GUSSET_MODEL"),
) -> None:
    """Verified blast radius of a change — every claim checked against the graph."""
    import uuid

    from dotenv import load_dotenv

    load_dotenv()
    from langchain_anthropic import ChatAnthropic
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.probe import make_callbacks, trace_url_hint
    from gusset.workflows.impact import build_impact_graph
    from gusset.workflows.seeds import seeds_from_diff

    db = _db_path(db)
    seed_qualnames = list(symbol)
    if diff:
        seed_qualnames += seeds_from_diff(repo, diff, db)
    if not seed_qualnames:
        typer.echo("No seeds: pass --symbol and/or --diff.", err=True)
        raise typer.Exit(1)

    session_id = f"impact-{uuid.uuid4().hex[:12]}"
    callbacks = make_callbacks(session_id, tags=["workflow:impact"])
    checkpoint_dir = db.parent / "checkpoints.db"
    with SqliteSaver.from_conn_string(str(checkpoint_dir)) as saver:
        graph = build_impact_graph(ChatAnthropic(model=model_name), checkpointer=saver)
        config = {"configurable": {"thread_id": session_id}, "callbacks": callbacks}
        state = graph.invoke(
            {"db_path": str(db), "seed_qualnames": seed_qualnames}, config
        )
        if state.get("halt_reason"):
            typer.echo(f"Halted: {state['halt_reason']}", err=True)
            raise typer.Exit(1)

        if "__interrupt__" in state:
            draft = state["__interrupt__"][0].value["draft"]
            if yes:
                state = graph.invoke(Command(resume=True), config)
            else:
                typer.echo(draft)
                approved = typer.confirm("\nApprove this report?")
                state = graph.invoke(Command(resume=approved), config)
                if not approved:
                    typer.echo("Rejected — nothing written.", err=True)
                    raise typer.Exit(1)

    out.write_text(state["draft"] + "\n")
    verified, dropped = len(state.get("verified", [])), len(state.get("dropped", []))
    typer.echo(f"wrote {out} — {verified} verified, {dropped} dropped at the gate")
    if (url := trace_url_hint(session_id)) is not None:
        typer.echo(f"trace: {url}")


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
