"""Self-healing: the PandaProbe harness wrapped around workflow runs.

Mapping (docs/design.md):
  harness session  = one workflow run
  harness turn     = one verified ring cycle (or the synthesis step)
  verifier         = the oracle (min of closure_recall and summary_grounding)
  replay           = re-run the workflow on the same graph db + seeds

Turn hooks are fire-and-forget sync calls; settle() is awaited once at the
end of a run. Disabled (all no-ops) unless BOTH PandaProbe credentials and
HARNESS_REPAIR_MODEL are present — the repair model is billable, so it is
never defaulted.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from gusset.probe.tracing import make_callbacks, probe_enabled


def _oracle_verifier(session_id: str, end_state: Any) -> float | None:
    """Ground truth for the harness: recompute oracle scores from end_state.

    Outcome verification only applies to outcomes: mid-run turns are
    incomplete by construction (ring N of M), and scoring them as final
    would teach the repair agent phantom lessons — None means "no ground
    truth for this turn", and the trajectory gate handles shape instead.
    """
    if not isinstance(end_state, dict):
        return None
    payload = end_state.get("gusset") or {}
    db_path, state = payload.get("db_path"), payload.get("state")
    if not db_path or not isinstance(state, dict) or not Path(db_path).exists():
        return None
    if payload.get("node") != "synthesize" or not state.get("draft"):
        return None
    from gusset.oracle import score_impact_run

    by_name = {s.name: s.value for s in score_impact_run(state, db_path)}
    return min(by_name["closure_recall"], by_name["summary_grounding"])


class SelfHealing:
    """Per-run harness scope. Instantiate via create(); safe to use when off."""

    def __init__(self, harness, session_id: str):
        self._harness = harness
        self.session_id = session_id
        self._turn_index = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the event loop harness tasks must run on. The workflow itself
        runs in a worker thread (asyncio.to_thread), so turn hooks marshal
        their on_turn_end onto this loop — ensure_future needs it running."""
        self._loop = loop

    @property
    def enabled(self) -> bool:
        return self._harness is not None

    @classmethod
    def create(cls, session_id: str) -> "SelfHealing":
        repair_model = os.environ.get("HARNESS_REPAIR_MODEL")
        if not (probe_enabled() and repair_model):
            return cls(None, session_id)
        try:
            from pandaprobe_harness import Harness, HarnessConfig

            # HarnessConfig does not read HARNESS_ROOT itself, and its
            # baked-in default is an unwritable /harness — always pass it.
            root = Path(os.environ.get("HARNESS_ROOT", ".gusset/harness"))
            harness = Harness.create(
                HarnessConfig(repair_model=repair_model, harness_root=root),
                replay=_replay_impact,
                verifier=_oracle_verifier,
            )
            return cls(harness, session_id)
        except Exception as exc:  # noqa: BLE001 — healing must never break the run
            import sys

            print(f"gusset: self-healing disabled ({exc})", file=sys.stderr)
            return cls(None, session_id)

    def system_preamble(self) -> str:
        if not self.enabled:
            return ""
        return self._harness.system_context(self.session_id)

    def turn_hook(self, node: str, state: dict) -> None:
        """Passed to build_impact_graph(turn_hook=...); called per turn node."""
        if not self.enabled:
            return
        self._turn_index += 1
        payload = self._turn_payload(node, state)
        if self._loop is not None:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is not self._loop:
                self._loop.call_soon_threadsafe(self._harness.on_turn_end, payload)
                return
        self._harness.on_turn_end(payload)

    def _turn_payload(self, node: str, state: dict) -> dict:
        return {
            "session_id": self.session_id,
            "turn_index": self._turn_index,
            "end_state": {
                "gusset": {
                    "node": node,
                    "db_path": state.get("db_path"),
                    "state": {
                        k: state.get(k)
                        for k in ("seeds", "verified", "dropped", "draft")
                    },
                },
            },
        }

    async def settle(self) -> dict | None:
        """Await evaluation (and any repair episode) for this session.

        Must run on the SAME event loop that was running when turn_hook
        fired — the harness schedules eval tasks onto it, and a different
        loop would destroy them pending. The CLI guarantees this by
        wrapping the whole run in one asyncio.run().
        """
        if not self.enabled:
            return None
        result = await self._harness.settle(self.session_id)
        # settle deliberately does not join in-flight evaluation tasks;
        # refresh does — without it they die with the event loop.
        await self._harness.refresh(self.session_id)
        summary: dict = {"gate_breached": False, "repair_status": None}
        if result.report is not None:
            summary["gate_breached"] = bool(getattr(result.report, "gate_breached", False))
        if result.repair is not None:
            summary["repair_status"] = str(getattr(result.repair, "status", None))
        return summary


def _replay_impact(case, context) -> str:
    """Harness replay hook: re-run the impact workflow for a captured case.

    Deterministic substrate makes this honest — same graph db, same seeds,
    fresh session so the validation round can score the rerun's traces.
    """
    payload = (getattr(case, "end_state", None) or {}).get("gusset") or {}
    db_path, state = payload.get("db_path"), payload.get("state") or {}
    seeds = state.get("seeds") or []
    if not db_path or not seeds:
        raise ValueError("replay case missing gusset db_path/seeds")

    from langchain_anthropic import ChatAnthropic
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from gusset.workflows.impact import build_impact_graph

    session_id = f"impact-replay-{uuid.uuid4().hex[:12]}"
    heal = SelfHealing.create(session_id)
    with SqliteSaver.from_conn_string(":memory:") as saver:
        graph = build_impact_graph(
            ChatAnthropic(model=os.environ.get("GUSSET_MODEL", "claude-opus-5")),
            checkpointer=saver,
            system_preamble=heal.system_preamble(),
            turn_hook=heal.turn_hook,
        )
        config = {
            "configurable": {"thread_id": session_id},
            "callbacks": make_callbacks(session_id, tags=["workflow:impact", "replay"]),
        }
        result = graph.invoke({"db_path": db_path, "seed_qualnames": seeds}, config)
        if "__interrupt__" in result:
            graph.invoke(Command(resume=True), config)
    return session_id
