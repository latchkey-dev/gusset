"""gusset.toml — the invariant declarations a repo installs.

Example:

    [invariants.impact-on-pr]
    workflow = "impact"
    trigger  = "pull_request"
    autonomy = "comment"          # its CURRENT level; the ladder moves it
    max_autonomy = "comment"      # ceiling this invariant may ever earn

    [invariants.deadcode-zero]
    workflow = "deadcode"
    trigger  = "cron"
    autonomy = "report"
    max_autonomy = "propose"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from gusset.supervisor.ladder import Level

VALID_TRIGGERS = {"pull_request", "push", "cron", "manual"}
VALID_WORKFLOWS = {"impact", "atlas", "deadcode", "docs-drift"}


@dataclass
class Invariant:
    name: str
    workflow: str
    trigger: str
    autonomy: Level
    max_autonomy: Level
    # deterministic pre-filters — the graph decides whether to wake the LLM
    min_changed_symbols: int = 1
    settings: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.workflow not in VALID_WORKFLOWS:
            raise ValueError(f"{self.name}: unknown workflow {self.workflow!r}")
        if self.trigger not in VALID_TRIGGERS:
            raise ValueError(f"{self.name}: unknown trigger {self.trigger!r}")
        if self.autonomy > self.max_autonomy:
            raise ValueError(
                f"{self.name}: autonomy {self.autonomy.name} exceeds "
                f"max_autonomy {self.max_autonomy.name}"
            )


@dataclass
class GussetConfig:
    invariants: list[Invariant]

    def for_trigger(self, trigger: str) -> list[Invariant]:
        return [inv for inv in self.invariants if inv.trigger == trigger]

    def get(self, name: str) -> Invariant | None:
        return next((i for i in self.invariants if i.name == name), None)


DEFAULT_TOML = """\
# Gusset invariants — the truths this repo keeps true.
# autonomy is the invariant's CURRENT level; Gusset's ladder raises it only
# on sustained eval scores and lowers it on regression. max_autonomy is the
# ceiling a human grants; Gusset never raises that itself.

[invariants.impact-on-pr]
workflow = "impact"
trigger = "pull_request"
autonomy = "comment"          # non-destructive, visible value on day one
max_autonomy = "comment"

[invariants.atlas-freshness]
workflow = "atlas"
trigger = "push"
autonomy = "report"           # earns "propose" through the ladder
max_autonomy = "propose"

[invariants.deadcode-zero]
workflow = "deadcode"
trigger = "cron"
autonomy = "report"
max_autonomy = "propose"

[invariants.docs-drift]
workflow = "docs-drift"
trigger = "cron"
autonomy = "report"
max_autonomy = "propose"
"""


def load_config(path: str | Path = "gusset.toml") -> GussetConfig:
    data = tomllib.loads(Path(path).read_text())
    invariants = []
    for name, spec in (data.get("invariants") or {}).items():
        spec = dict(spec)
        invariants.append(
            Invariant(
                name=name,
                workflow=spec.pop("workflow"),
                trigger=spec.pop("trigger"),
                autonomy=Level.parse(spec.pop("autonomy", "report")),
                max_autonomy=Level.parse(spec.pop("max_autonomy", "report")),
                min_changed_symbols=spec.pop("min_changed_symbols", 1),
                settings=spec,
            )
        )
    if not invariants:
        raise ValueError(f"{path}: no [invariants.*] tables found")
    return GussetConfig(invariants)
