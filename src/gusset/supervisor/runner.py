"""The supervisor runner: event in, receipts out.

    event -> subscribed invariants -> deterministic guards -> workflow
          -> oracle scores -> ladder record/evaluate -> scoped action

Every skipped invariant produces a receipt naming the guard that stopped
it — silent inaction would be indistinguishable from failure.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from gusset.supervisor.actions import ActionReceipt, deliver
from gusset.supervisor.config import GussetConfig, Invariant
from gusset.supervisor.ladder import Ladder, Level


@dataclass
class Event:
    trigger: str                 # pull_request | push | cron | manual
    repo_root: Path
    pr_number: int | None = None
    diff_range: str | None = None


@dataclass
class RunReceipt:
    invariant: str
    outcome: str                 # "ran" | "skipped" | "errored"
    detail: str
    action: ActionReceipt | None = None
    scores: dict | None = None
    level_change: str | None = None


def handle_event(
    event: Event,
    config: GussetConfig,
    *,
    db_path: Path,
    ladder: Ladder | None = None,
    out_dir: Path = Path(".gusset/out"),
) -> list[RunReceipt]:
    ladder = ladder or Ladder(event.repo_root / ".gusset" / "ladder.jsonl")
    receipts: list[RunReceipt] = []
    for inv in config.for_trigger(event.trigger):
        receipts.append(
            _run_invariant(inv, event, db_path=db_path, ladder=ladder, out_dir=out_dir)
        )
    return receipts


def _run_invariant(
    inv: Invariant, event: Event, *, db_path: Path, ladder: Ladder, out_dir: Path
) -> RunReceipt:
    # -- deterministic guards: is the LLM worth waking? ---------------------
    seeds: list[str] = []
    if inv.workflow == "impact":
        if not event.diff_range:
            return RunReceipt(inv.name, "skipped", "guard: no diff in event")
        from gusset.workflows.seeds import seeds_from_diff

        seeds = seeds_from_diff(event.repo_root, event.diff_range, db_path)
        if len(seeds) < inv.min_changed_symbols:
            return RunReceipt(
                inv.name, "skipped",
                f"guard: {len(seeds)} changed symbols < {inv.min_changed_symbols}",
            )

    level = ladder.current_level(inv.name, inv.autonomy)
    session_id = f"{inv.workflow}-{uuid.uuid4().hex[:12]}"

    # -- run the workflow ----------------------------------------------------
    try:
        result = _execute_workflow(inv, event, db_path, seeds, session_id)
    except ValueError as exc:
        # An unwired workflow is a loud, receipted skip — one broken
        # invariant must not take down the rest of the event.
        return RunReceipt(inv.name, "skipped", str(exc))
    except Exception as exc:  # noqa: BLE001
        # Provider weather (529 storms, timeouts) on one invariant must not
        # fail the whole event: record it, run the rest, let the next
        # trigger retry. NOT ladder-recorded — an errored run is missing
        # data, not evidence of bad quality.
        return RunReceipt(inv.name, "errored", f"{type(exc).__name__}: {exc}")
    if result is None:
        return RunReceipt(inv.name, "skipped", "guard: nothing to do")
    body, scores, commit_paths = result

    # -- record scores, evaluate the ladder ---------------------------------
    ladder.record_run(inv.name, scores)
    decision = ladder.evaluate(inv.name, inv.autonomy, inv.max_autonomy)
    level = decision.level

    action = deliver(
        inv.name, level, body,
        artifact_path=out_dir / f"{inv.name}.md",
        pr_number=event.pr_number,
        branch=f"gusset/{inv.name}" if level >= Level.PROPOSE else None,
        commit_paths=commit_paths if level >= Level.PROPOSE else None,
        title=f"gusset: {inv.name}",
    )
    return RunReceipt(
        inv.name, "ran", f"session {session_id}", action=action, scores=scores,
        level_change=decision.reason if decision.changed else None,
    )


def _execute_workflow(
    inv: Invariant, event: Event, db_path: Path, seeds: list[str], session_id: str
):
    """Returns (report_body, scores, commit_paths) or None for nothing-to-do."""
    if inv.workflow == "deadcode":
        from gusset.graph import GraphStore

        store = GraphStore(db_path)
        try:
            dead = store.dead_symbols()
        finally:
            store.close()
        if not dead:
            return None
        body = "# Dead code\n\nSymbols with no incoming edges:\n\n" + "\n".join(
            f"- `{s.qualname}` ({s.path}:{s.start_line})" for s in dead
        )
        return body, {"deadcode_precision": 1.0}, []

    if inv.workflow == "impact":
        state = _run_impact(event, db_path, seeds, session_id)
        if state.get("halt_reason"):
            return None
        from gusset.oracle import score_impact_run

        scores = {s.name: s.value for s in score_impact_run(state, db_path)}
        body = _with_blast_image(state, event, session_id) or state["draft"]
        return body, scores, []

    if inv.workflow == "atlas":
        state = _run_graph_workflow(
            "atlas", {"db_path": str(db_path)}, session_id, with_model=True
        )
        if state.get("halt_reason"):
            return None
        from gusset.oracle import score_atlas_run

        scores = {s.name: s.value for s in score_atlas_run(state, db_path)}
        atlas_out = event.repo_root / "docs" / "architecture.md"
        atlas_out.parent.mkdir(parents=True, exist_ok=True)
        atlas_out.write_text(state["draft"] + "\n")
        return state["draft"], scores, [atlas_out]

    if inv.workflow == "docs-drift":
        from gusset.graph.indexer import SKIP_DIRS

        skip = SKIP_DIRS | {".gusset"}
        docs = {
            str(p.relative_to(event.repo_root)): p.read_text()
            for p in sorted(event.repo_root.rglob("*.md"))
            if not (skip & set(p.relative_to(event.repo_root).parts))
        }
        if not docs:
            return None
        state = _run_graph_workflow(
            "docs-drift", {"db_path": str(db_path), "docs": docs}, session_id,
            repo_root=event.repo_root,
            with_model=bool(__import__("os").environ.get("ANTHROPIC_API_KEY")),
        )
        if not state.get("stale"):
            return None  # nothing drifted — receipted as a guard skip upstream
        scores = {
            "drift_found": 1.0,
            "claims_checked": float(len(state.get("claims", []))),
        }
        return state["draft"], scores, []

    raise ValueError(f"workflow {inv.workflow!r} not yet wired into the supervisor")


def _with_blast_image(state: dict, event: Event, session_id: str) -> str | None:
    """Prepend the blast-radius SVG to the impact comment.

    GitHub renders images in comments only from fetchable URLs, so the SVG
    is committed to the PR's own branch and referenced raw. Every failure
    mode degrades to the text-only comment — never a broken image.
    """
    import subprocess

    try:
        from gusset.serve.blastimage import blast_svg

        svg = blast_svg(
            state.get("seeds") or [],
            state.get("verified") or [],
            state.get("dropped") or [],
        )
        rel = f".gusset/out/blast-{session_id}.svg"
        out_path = event.repo_root / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(svg)
        if event.pr_number is None:
            return None  # local run: file written, no comment to decorate
        import os

        # In Actions, pull_request checkouts are detached HEAD — the PR's
        # real branch is in GITHUB_HEAD_REF (live-run bug: rev-parse gave
        # "HEAD" and the push silently failed, comment shipped imageless).
        branch = os.environ.get("GITHUB_HEAD_REF") or subprocess.run(
            ["git", "-C", str(event.repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        if not branch or branch == "HEAD":
            return None
        ident = ["-c", "user.name=gusset[bot]",
                 "-c", "user.email=gusset@users.noreply.github.com"]
        # -f: .gusset/ is gitignored; the image is a deliberate exception
        # (live-run bug: plain add staged nothing and the commit failed).
        subprocess.run(["git", "-C", str(event.repo_root), "add", "-f", rel],
                       check=True, capture_output=True, timeout=15)
        subprocess.run(
            ["git", "-C", str(event.repo_root), *ident, "commit", "-m",
             f"gusset: blast-radius image for {session_id}"],
            check=True, capture_output=True, timeout=15,
        )
        subprocess.run(
            ["git", "-C", str(event.repo_root), "push", "origin",
             f"HEAD:{branch}"],
            check=True, capture_output=True, timeout=60,
        )
        slug = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            capture_output=True, text=True, timeout=15, cwd=event.repo_root,
        ).stdout.strip()
        if not slug or not branch:
            return None
        url = f"https://raw.githubusercontent.com/{slug}/{branch}/{rel}"
        return f"![blast radius]({url})\n\n{state['draft']}"
    except Exception as exc:  # noqa: BLE001 — the image is garnish, never a failure
        import sys

        print(f"gusset: blast image skipped ({type(exc).__name__}: {exc})",
              file=sys.stderr)
        return None


def _run_graph_workflow(
    name: str, inputs: dict, session_id: str, *, with_model: bool, repo_root=None
) -> dict:
    """Shared runner for atlas/docs-drift: same loop discipline as impact."""
    import asyncio
    import os

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.probe import make_callbacks
    from gusset.probe.selfheal import SelfHealing

    if name == "atlas":
        from gusset.workflows.atlas import build_atlas_graph as build
    else:
        from functools import partial

        from gusset.workflows.docsdrift import build_docsdrift_graph, load_allowlist

        build = partial(build_docsdrift_graph,
                        allowlist=load_allowlist(repo_root) if repo_root else None)

    model = None
    if with_model:
        from gusset.llm import make_model

        model = make_model()

    async def _run() -> dict:
        heal = SelfHealing.create(session_id)
        heal.bind_loop(asyncio.get_running_loop())
        with SqliteSaver.from_conn_string(":memory:") as saver:
            graph = build(
                model, checkpointer=saver,
                system_preamble=heal.system_preamble(), turn_hook=heal.turn_hook,
            )
            config = {
                "configurable": {"thread_id": session_id},
                "callbacks": make_callbacks(
                    session_id, tags=[f"workflow:{name}", "supervisor"]
                ),
            }
            state = await asyncio.to_thread(graph.invoke, inputs, config)
            if "__interrupt__" in state:
                state = await asyncio.to_thread(graph.invoke, Command(resume=True), config)
            await heal.settle()
            return state

    return asyncio.run(_run())


def _run_impact(event: Event, db_path: Path, seeds: list[str], session_id: str) -> dict:
    import asyncio
    import os

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.llm import make_model
    from gusset.probe import make_callbacks
    from gusset.probe.selfheal import SelfHealing
    from gusset.workflows.impact import build_impact_graph

    async def _run() -> dict:
        heal = SelfHealing.create(session_id)
        heal.bind_loop(asyncio.get_running_loop())
        with SqliteSaver.from_conn_string(
            str(db_path.parent / "checkpoints.db")
        ) as saver:
            graph = build_impact_graph(
                make_model(),
                checkpointer=saver,
                system_preamble=heal.system_preamble(),
                turn_hook=heal.turn_hook,
            )
            config = {
                "configurable": {"thread_id": session_id},
                "callbacks": make_callbacks(
                    session_id, tags=["workflow:impact", "supervisor"]
                ),
            }
            state = await asyncio.to_thread(
                graph.invoke, {"db_path": str(db_path), "seed_qualnames": seeds}, config
            )
            if "__interrupt__" in state:
                # Autonomous mode: the human gate moves to the PR review.
                state = await asyncio.to_thread(graph.invoke, Command(resume=True), config)
            await heal.settle()
            return state

    return asyncio.run(_run())


def receipts_json(receipts: list[RunReceipt]) -> str:
    return json.dumps([
        {
            "invariant": r.invariant,
            "outcome": r.outcome,
            "detail": r.detail,
            "action": (r.action.action if r.action else None),
            "action_detail": (r.action.detail if r.action else None),
            "scores": r.scores,
            "level_change": r.level_change,
        }
        for r in receipts
    ], indent=2)
