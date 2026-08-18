"""Seed resolution from a git diff: changed lines -> overlapping symbols.

Deterministic — this runs before any LLM is woken, and its output is the
only thing the impact workflow is allowed to treat as ground truth input.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from gusset.graph import GraphStore

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(repo: Path, diff_range: str) -> dict[str, set[int]]:
    """{repo-relative path: set of new-side line numbers} for a git range."""
    out = subprocess.run(
        ["git", "-C", str(repo), "diff", "--unified=0", diff_range, "--"],
        capture_output=True, text=True, timeout=60, check=True,
    )
    changes: dict[str, set[int]] = {}
    current: str | None = None
    for line in out.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+++ /dev/null"):
            current = None
        elif current is not None and (m := _HUNK.match(line)):
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count > 0:
                changes.setdefault(current, set()).update(range(start, start + count))
            else:  # pure deletion: attribute to the line above the removal site
                changes.setdefault(current, set()).add(max(start, 1))
    return changes


def seeds_from_diff(repo: Path, diff_range: str, db_path: Path) -> list[str]:
    store = GraphStore(db_path)
    try:
        seeds: list[str] = []
        for path, lines in changed_lines(repo, diff_range).items():
            for sym in store.symbols_overlapping(path, lines):
                if sym.qualname not in seeds:
                    seeds.append(sym.qualname)
        return seeds
    finally:
        store.close()
