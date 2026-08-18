"""Condition B — the graph-engineered workflow (build_impact_graph).

Runs the compiled impact graph per seed, resumes through the human-gate
interrupt with Command(resume=True), and returns the final state plus token
usage (threaded through a callback handler, since the workflow calls the
model internally).
"""

from __future__ import annotations

import time

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from gusset.workflows.impact import build_impact_graph


class UsageTally(BaseCallbackHandler):
    """Accumulates usage_metadata from every LLM call in the run."""

    def __init__(self) -> None:
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read": 0,
                      "cache_creation": 0, "llm_calls": 0}

    def on_llm_end(self, response, **kwargs) -> None:
        for gen_list in response.generations:
            for gen in gen_list:
                um = getattr(getattr(gen, "message", None), "usage_metadata", None)
                if not um:
                    continue
                self.usage["input_tokens"] += um.get("input_tokens", 0)
                self.usage["output_tokens"] += um.get("output_tokens", 0)
                details = um.get("input_token_details") or {}
                self.usage["cache_read"] += details.get("cache_read", 0)
                self.usage["cache_creation"] += details.get("cache_creation", 0)
                self.usage["llm_calls"] += 1


def run_gusset(question: dict, model) -> dict:
    """One seed through the impact workflow; approve the draft at the gate."""
    tally = UsageTally()
    graph = build_impact_graph(model, checkpointer=InMemorySaver())
    config = {
        "configurable": {"thread_id": f"{question['corpus']}:{question['seed']}"},
        "callbacks": [tally],
    }
    t0 = time.perf_counter()
    state = graph.invoke(
        {"db_path": question["db_path"], "seed_qualnames": [question["seed"]]},
        config,
    )
    if "__interrupt__" in state:
        state = graph.invoke(Command(resume=True), config)
    wall = round(time.perf_counter() - t0, 2)

    return {
        "state": {
            "seeds": state.get("seeds", []),
            "verified": state.get("verified", []),
            "dropped": state.get("dropped", []),
            "aggregated_modules": state.get("aggregated_modules", []),
            "draft": state.get("draft", ""),
            "halt_reason": state.get("halt_reason", ""),
            "approved": state.get("approved"),
        },
        "claimed": [c["qualname"] for c in state.get("verified", [])],
        "usage": tally.usage,
        "wall_seconds": wall,
    }
