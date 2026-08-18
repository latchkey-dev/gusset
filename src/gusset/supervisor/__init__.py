"""The supervisor: Gusset's own execution graph, one level up.

Events (PR, push, cron) route through deterministic policy guards to
workflow subgraphs, whose outputs flow to capability-scoped actions.
No LLM is consulted anywhere in this package — the graph decides
whether to wake the LLM, never the other way around.
"""

from gusset.supervisor.config import GussetConfig, Invariant, load_config
from gusset.supervisor.ladder import Ladder, Level

__all__ = ["GussetConfig", "Invariant", "Ladder", "Level", "load_config"]
