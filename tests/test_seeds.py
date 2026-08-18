"""Diff -> seed resolution against a real throwaway git repo."""

import shutil
import subprocess
from pathlib import Path

from gusset.graph.indexer import index_repo
from gusset.workflows.seeds import seeds_from_diff

FIXTURE = Path(__file__).parent / "fixtures" / "pyproj"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "PATH": "/usr/bin:/bin",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )


def test_seeds_from_diff(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    git(repo, "init", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "base")

    lib = repo / "pkg" / "lib.py"
    text = lib.read_text().replace("return x * 2", "return x * 3")
    lib.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "change _internal")

    db = tmp_path / "graph.db"
    index_repo(repo, db)

    seeds = seeds_from_diff(repo, "HEAD~1", db)
    assert seeds == ["pkg.lib._internal"]
