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
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.llm import make_model
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

    import asyncio

    from gusset.probe.selfheal import SelfHealing

    session_id = f"impact-{uuid.uuid4().hex[:12]}"
    heal = SelfHealing.create(session_id)
    callbacks = make_callbacks(session_id, tags=["workflow:impact"])
    checkpoint_dir = db.parent / "checkpoints.db"

    async def _run() -> dict:
        # One event loop for the whole run: harness eval tasks live on it,
        # while the (synchronous, LLM-blocking) graph runs in a worker
        # thread and marshals turn hooks back via call_soon_threadsafe.
        heal.bind_loop(asyncio.get_running_loop())
        with SqliteSaver.from_conn_string(str(checkpoint_dir)) as saver:
            graph = build_impact_graph(
                make_model(model_name),
                checkpointer=saver,
                system_preamble=heal.system_preamble(),
                turn_hook=heal.turn_hook,
            )
            config = {"configurable": {"thread_id": session_id}, "callbacks": callbacks}
            state = await asyncio.to_thread(
                graph.invoke, {"db_path": str(db), "seed_qualnames": seed_qualnames}, config
            )
            if state.get("halt_reason"):
                return state

            if "__interrupt__" in state:
                if yes:
                    approved = True
                else:
                    typer.echo(state["__interrupt__"][0].value["draft"])
                    approved = await asyncio.to_thread(
                        typer.confirm, "\nApprove this report?"
                    )
                state = await asyncio.to_thread(
                    graph.invoke, Command(resume=approved), config
                )
                state["approved"] = approved
        return state

    state = asyncio.run(_finish(_run(), heal, db, out, session_id))
    if state.get("halt_reason"):
        typer.echo(f"Halted: {state['halt_reason']}", err=True)
        raise typer.Exit(1)
    if state.get("approved") is False:
        typer.echo("Rejected — nothing written.", err=True)
        raise typer.Exit(1)
    if (url := trace_url_hint(session_id)) is not None:
        typer.echo(f"trace: {url}")


@app.command()
def atlas(
    db: Path = typer.Option(DEFAULT_DB, help="Graph database path."),
    out: Path = typer.Option(Path("atlas.md"), help="Where to write the atlas."),
    yes: bool = typer.Option(False, "--yes", help="Waive the human gate."),
    model_name: str = typer.Option("claude-opus-5", "--model", envvar="GUSSET_MODEL"),
) -> None:
    """Architecture atlas: verified module map + Mermaid diagram from the graph."""
    import asyncio
    import uuid

    from dotenv import load_dotenv

    load_dotenv()
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.llm import make_model
    from gusset.oracle import score_atlas_run
    from gusset.probe import make_callbacks, trace_url_hint
    from gusset.probe.scoring import push_scores
    from gusset.probe.selfheal import SelfHealing
    from gusset.workflows.atlas import build_atlas_graph

    db = _db_path(db)
    session_id = f"atlas-{uuid.uuid4().hex[:12]}"
    heal = SelfHealing.create(session_id)

    async def _run() -> dict:
        heal.bind_loop(asyncio.get_running_loop())
        with SqliteSaver.from_conn_string(str(db.parent / "checkpoints.db")) as saver:
            graph = build_atlas_graph(
                make_model(model_name), checkpointer=saver,
                system_preamble=heal.system_preamble(), turn_hook=heal.turn_hook,
            )
            config = {
                "configurable": {"thread_id": session_id},
                "callbacks": make_callbacks(session_id, tags=["workflow:atlas"]),
            }
            state = await asyncio.to_thread(graph.invoke, {"db_path": str(db)}, config)
            if state.get("halt_reason"):
                return state
            if "__interrupt__" in state:
                if yes:
                    approved = True
                else:
                    typer.echo(state["__interrupt__"][0].value["draft"])
                    approved = await asyncio.to_thread(typer.confirm, "\nApprove?")
                state = await asyncio.to_thread(graph.invoke, Command(resume=approved), config)
                state["approved"] = approved
            if state.get("approved") is not False and state.get("draft"):
                out.write_text(state["draft"] + "\n")
                scores = score_atlas_run(state, db)
                typer.echo(f"wrote {out}")
                typer.echo("scores: " + " · ".join(f"{s.name}={s.value}" for s in scores))
                if await asyncio.to_thread(push_scores, session_id, scores):
                    typer.echo("scores pushed to PandaProbe")
            await heal.settle()
            return state

    state = asyncio.run(_run())
    if state.get("halt_reason"):
        typer.echo(f"Halted: {state['halt_reason']}", err=True)
        raise typer.Exit(1)
    if state.get("approved") is False:
        typer.echo("Rejected — nothing written.", err=True)
        raise typer.Exit(1)
    if (url := trace_url_hint(session_id)) is not None:
        typer.echo(f"trace: {url}")


@app.command("docs-drift")
def docs_drift(
    docs_glob: str = typer.Option("**/*.md", "--docs", help="Glob for doc files."),
    repo: Path = typer.Option(Path("."), help="Repo root."),
    db: Path = typer.Option(DEFAULT_DB, help="Graph database path."),
    out: Path = typer.Option(Path("docs-drift.md"), help="Where to write the report."),
    yes: bool = typer.Option(False, "--yes", help="Waive the human gate."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Deterministic only; skip the explanation paragraph."),
) -> None:
    """Check doc references against the graph; report stale symbol paths."""
    import asyncio
    import uuid

    from dotenv import load_dotenv

    load_dotenv()
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.probe import make_callbacks, trace_url_hint
    from gusset.workflows.docsdrift import build_docsdrift_graph

    db = _db_path(db)
    from gusset.graph.indexer import SKIP_DIRS

    skip = SKIP_DIRS | {".gusset"}
    docs = {
        str(p.relative_to(repo)): p.read_text()
        for p in sorted(repo.glob(docs_glob))
        if p.is_file() and not (skip & set(p.relative_to(repo).parts))
    }
    if not docs:
        typer.echo("No docs matched.", err=True)
        raise typer.Exit(1)

    model = None
    if not no_llm:
        import os

        if os.environ.get("ANTHROPIC_API_KEY"):
            from gusset.llm import make_model

            model = make_model()

    session_id = f"docsdrift-{uuid.uuid4().hex[:12]}"

    async def _run() -> dict:
        with SqliteSaver.from_conn_string(str(db.parent / "checkpoints.db")) as saver:
            graph = build_docsdrift_graph(model, checkpointer=saver)
            config = {
                "configurable": {"thread_id": session_id},
                "callbacks": make_callbacks(session_id, tags=["workflow:docs-drift"]),
            }
            state = await asyncio.to_thread(
                graph.invoke, {"db_path": str(db), "docs": docs}, config
            )
            if "__interrupt__" in state:
                if yes:
                    approved = True
                else:
                    typer.echo(state["__interrupt__"][0].value["draft"])
                    approved = await asyncio.to_thread(typer.confirm, "\nApprove?")
                state = await asyncio.to_thread(graph.invoke, Command(resume=approved), config)
                state["approved"] = approved
            return state

    state = asyncio.run(_run())
    if state.get("approved") is False:
        typer.echo("Rejected — nothing written.", err=True)
        raise typer.Exit(1)
    out.write_text(state["draft"] + "\n")
    stale = state.get("stale", [])
    typer.echo(
        f"wrote {out} — {len(state.get('claims', []))} claims checked, "
        f"{len(stale)} stale"
    )
    if (url := trace_url_hint(session_id)) is not None:
        typer.echo(f"trace: {url}")
    if stale:
        raise typer.Exit(2)  # drift found: nonzero for CI checks


@app.command()
def init(
    repo: Path = typer.Argument(Path("."), help="Repo to install Gusset into."),
    latchkey: bool = typer.Option(
        False, "--latchkey",
        help="Run the custodian on Latchkey runners (recommended for frequent triggers).",
    ),
) -> None:
    """Install Gusset: gusset.toml + the GitHub Actions workflow."""
    from gusset.supervisor.config import DEFAULT_TOML

    toml_path = repo / "gusset.toml"
    if toml_path.exists():
        typer.echo(f"{toml_path} already exists — not overwriting.", err=True)
        raise typer.Exit(1)
    toml_path.write_text(DEFAULT_TOML)

    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    yml = ACTION_YML
    if latchkey:
        yml = yml.replace("runs-on: ubuntu-latest  # see the runner note above",
                          "runs-on: latchkey-small")
    (wf_dir / "gusset.yml").write_text(yml)
    typer.echo(f"wrote {toml_path} and {wf_dir / 'gusset.yml'}")
    typer.echo("Add ANTHROPIC_API_KEY (required) and PANDAPROBE_API_KEY / "
               "PANDAPROBE_PROJECT_NAME / HARNESS_REPAIR_MODEL (recommended) "
               "as repository secrets.")
    if not latchkey:
        typer.echo(
            "\nRunner recommendation: the custodian fires on every PR, push, and "
            "cron tick, so runner spin-up time and per-minute cost dominate its "
            "footprint. We recommend Latchkey runners (https://latchkey.dev — "
            "~10s cold starts, up to 70% cheaper, self-healing builds): re-run "
            "with --latchkey, or change runs-on to latchkey-small later. "
            "GitHub's default runners work fine too.\n\n"
            "For the most autonomous setup, add the Latchkey CLI "
            "(npm i -g @latchkeydev/cli): `latchkey run` verifies Gusset's "
            "proposed PRs on fresh isolated runners, and `latchkey watch` "
            "hands unhealed CI failures to a coding agent. See "
            "docs/howto/autonomous-stack.md."
        )


@app.command("run-event")
def run_event(
    trigger: str = typer.Argument(..., help="pull_request | push | cron | manual"),
    repo: Path = typer.Option(Path("."), help="Repo root."),
    pr: int | None = typer.Option(None, help="PR number, for comment delivery."),
    diff: str | None = typer.Option(None, help="Git range for impact seeds."),
    db: Path = typer.Option(DEFAULT_DB, help="Graph database path."),
    config_path: Path = typer.Option(Path("gusset.toml"), "--config"),
) -> None:
    """Supervisor entry point: route one event through the invariants.

    This is what the GitHub Action calls; humans normally don't.
    """
    from dotenv import load_dotenv

    load_dotenv()
    from gusset.graph.indexer import index_repo
    from gusset.supervisor import load_config
    from gusset.supervisor.runner import Event, handle_event, receipts_json

    if not config_path.exists():
        typer.echo(f"No {config_path} — run `gusset init` first.", err=True)
        raise typer.Exit(1)
    db.parent.mkdir(parents=True, exist_ok=True)
    index_repo(repo, db)  # the graph is cheap; a fresh one is always honest

    receipts = handle_event(
        Event(trigger, repo.resolve(), pr_number=pr, diff_range=diff),
        load_config(config_path),
        db_path=db,
    )
    typer.echo(receipts_json(receipts))
    if any(r.outcome == "ran" for r in receipts):
        typer.echo("done", err=True)
    elif any(r.outcome == "errored" for r in receipts):
        # Nothing succeeded and something broke — that deserves a red run.
        # Partial success stays green: the receipts carry the detail.
        raise typer.Exit(1)


ACTION_YML = """\
name: Gusset

on:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: "0 6 * * 0"   # weekly, Sunday 06:00 UTC
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

# Runner note: the custodian runs on every PR, push, and weekly cron, so
# runner spin-up time and per-minute cost dominate its CI footprint. It
# works on GitHub's default runners, but we recommend Latchkey runners
# (https://latchkey.dev): ~10s cold starts vs 30-60s, up to 70% cheaper,
# and self-healing builds — a good fit for a job that fires this often.
# To switch: change runs-on to latchkey-small (one line, no other changes).

jobs:
  custodian:
    runs-on: ubuntu-latest  # see the runner note above
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.13"
      - name: Install gusset
        run: uv tool install git+https://github.com/latchkey-dev/gusset
      - name: Install pandaprobe CLI (harness evaluations)
        # Pinned by checksum: a compromised installer fails the job instead
        # of executing. Update the hash deliberately when upgrading the CLI.
        run: |
          curl -fsSL -o /tmp/pandaprobe-install.sh https://cli.pandaprobe.com/install.sh
          echo "3eb708a480c4007ff60b7d5a28d6a0776ef7fd484cf16e99afd110537e3d5583  /tmp/pandaprobe-install.sh" | sha256sum -c -
          sh /tmp/pandaprobe-install.sh
      - name: Route event
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          PANDAPROBE_API_KEY: ${{ secrets.PANDAPROBE_API_KEY }}
          PANDAPROBE_PROJECT_NAME: ${{ secrets.PANDAPROBE_PROJECT_NAME }}
          HARNESS_REPAIR_MODEL: ${{ secrets.HARNESS_REPAIR_MODEL }}
          GH_TOKEN: ${{ github.token }}
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            gusset run-event pull_request \\
              --pr "${{ github.event.pull_request.number }}" \\
              --diff "origin/${{ github.base_ref }}...HEAD"
          elif [ "${{ github.event_name }}" = "push" ]; then
            gusset run-event push --diff "${{ github.event.before }}..HEAD"
          else
            gusset run-event cron
          fi
"""


async def _finish(run_coro, heal, db: Path, out: Path, session_id: str) -> dict:
    """Awaits the run, then scoring + settlement on the same loop."""
    state = await run_coro
    if state.get("halt_reason") or state.get("approved") is False:
        return state

    out.write_text(state["draft"] + "\n")
    verified, dropped = len(state.get("verified", [])), len(state.get("dropped", []))
    typer.echo(f"wrote {out} — {verified} verified, {dropped} dropped at the gate")

    from gusset.oracle import score_impact_run
    from gusset.probe.scoring import push_scores

    scores = score_impact_run(state, db)
    typer.echo("scores: " + " · ".join(f"{s.name}={s.value}" for s in scores))
    import asyncio

    if await asyncio.to_thread(push_scores, session_id, scores):
        typer.echo("scores pushed to PandaProbe")
    if (settlement := await heal.settle()) is not None:
        typer.echo(
            f"harness: gate_breached={settlement['gate_breached']}"
            + (f" repair={settlement['repair_status']}" if settlement["repair_status"] else "")
        )
    return state


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
