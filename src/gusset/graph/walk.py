"""Directory walking that prunes rather than filters.

`Path.rglob` enumerates everything and leaves the caller to discard what it
does not want, so a repo with a populated `node_modules` pays for every
file in it — on every index, twice over. Pruning at the directory level
never descends in the first place.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path


def walk_files(root: Path, skip_dirs: set[str]) -> Iterator[Path]:
    """Every file under `root`, skipping `skip_dirs` subtrees entirely.

    Yields in a deterministic order so an index is reproducible.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        base = Path(dirpath)
        for filename in sorted(filenames):
            yield base / filename
