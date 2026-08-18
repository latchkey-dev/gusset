"""The autonomy ladder: permissions earned with eval scores, lost on regression.

Promotion is a deterministic rule over PandaProbe score history — never an
LLM judgment, never a human forgetting to flip a switch. Demotion needs
fewer bad runs than promotion needed good ones: trust is asymmetric.

The ladder decides LEVELS; it never performs actions. Action nodes check
the level at execution time.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class Level(enum.IntEnum):
    REPORT = 0    # write artifacts only
    COMMENT = 1   # comment on PRs
    PROPOSE = 2   # open PRs
    ACT = 3       # merge designated classes — humans grant this, never the ladder

    @classmethod
    def parse(cls, s: str) -> "Level":
        try:
            return cls[s.upper()]
        except KeyError:
            raise ValueError(f"unknown autonomy level: {s!r}") from None

    def __str__(self) -> str:
        return self.name.lower()


# Promotion: this many consecutive runs with min-score >= threshold.
PROMOTE_RUNS = 15
PROMOTE_THRESHOLD = 0.9
# Demotion: this many breaches within the last WINDOW runs.
DEMOTE_BREACHES = 3
DEMOTE_WINDOW = 5
DEMOTE_THRESHOLD = 0.8


@dataclass
class LadderDecision:
    level: Level
    changed: bool
    reason: str


class Ladder:
    """Score history + level state per invariant, in one JSONL ledger.

    The ledger is committed to the repo (like the harness workspace):
    autonomy decisions must survive ephemeral CI runners and be auditable
    in-repo. Scores also live in PandaProbe; the ledger is the local,
    deterministic record the decision rule reads.
    """

    def __init__(self, path: str | Path = ".gusset/ladder.jsonl"):
        self.path = Path(path)

    def record_run(self, invariant: str, scores: dict[str, float]) -> None:
        # Rate-style metrics are lower-is-better; normalize so min_score is
        # meaningful. Without this, a PERFECT run (gate_drop_rate=0.0) scored
        # min 0.0 and counted as a breach — found by the serve ladder view.
        normalized = {
            k: (1.0 - v if "drop_rate" in k or "hallucinated" in k else v)
            for k, v in scores.items()
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({
                "type": "run",
                "invariant": invariant,
                "min_score": min(normalized.values()) if normalized else 0.0,
                "scores": scores,
                "ts": datetime.now(timezone.utc).isoformat(),
            }) + "\n")

    def _entries(self, invariant: str) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("invariant") == invariant:
                out.append(d)
        return out

    def current_level(self, invariant: str, configured: Level) -> Level:
        """Configured level adjusted by recorded ladder events."""
        level = configured
        for e in self._entries(invariant):
            if e["type"] == "level":
                level = Level(e["level"])
        return level

    def evaluate(self, invariant: str, configured: Level, ceiling: Level) -> LadderDecision:
        """Apply the promotion/demotion rule and record any level change."""
        level = self.current_level(invariant, configured)
        runs = [e for e in self._entries(invariant) if e["type"] == "run"]

        recent = runs[-DEMOTE_WINDOW:]
        breaches = sum(1 for r in recent if r["min_score"] < DEMOTE_THRESHOLD)
        if level > Level.REPORT and breaches >= DEMOTE_BREACHES:
            new = Level(level - 1)
            self._record_level(invariant, new,
                               f"{breaches}/{len(recent)} recent runs below "
                               f"{DEMOTE_THRESHOLD} — demoted")
            return LadderDecision(new, True, "demoted on regression")

        if level < ceiling:
            streak = 0
            for r in reversed(runs):
                if r["min_score"] >= PROMOTE_THRESHOLD:
                    streak += 1
                else:
                    break
            if streak >= PROMOTE_RUNS:
                new = Level(level + 1)
                if new == Level.ACT:
                    # The ladder never grants ACT; only humans do, in config.
                    return LadderDecision(level, False,
                                          "at propose; act requires human grant")
                self._record_level(invariant, new,
                                   f"{streak} consecutive runs >= {PROMOTE_THRESHOLD}")
                return LadderDecision(new, True, f"promoted after {streak} clean runs")

        return LadderDecision(level, False, "no change")

    def _record_level(self, invariant: str, level: Level, reason: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({
                "type": "level",
                "invariant": invariant,
                "level": int(level),
                "reason": reason,
                "ts": datetime.now(timezone.utc).isoformat(),
            }) + "\n")
