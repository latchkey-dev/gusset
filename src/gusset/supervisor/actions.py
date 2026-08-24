"""Capability-scoped actions: what an invariant's output is allowed to become.

The level check lives HERE, at the moment of action — not in the caller's
good intentions. Every action returns a receipt dict for the run log, and
every refusal is a logged decision, never a silent skip.

GitHub interaction goes through the `gh` CLI: already authenticated in
Actions runners and on dev machines, no token plumbing in our code.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from gusset.supervisor.ladder import Level


@dataclass
class ActionReceipt:
    invariant: str
    level: Level
    action: str            # "artifact" | "comment" | "propose" | "refused"
    detail: str


def _gh(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=120,
        input=input_text,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {args[0]} failed: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def _compare_url(branch: str, base: str) -> str:
    """The 'open a PR for this branch' URL, or a plain instruction.

    `GITHUB_REPOSITORY` is set in every Actions run; locally we ask `gh`.
    If neither answers we say what to do rather than print a broken link —
    a wrong URL in a receipt is worse than no URL.
    """
    import os

    slug = os.environ.get("GITHUB_REPOSITORY", "")
    if not slug:
        try:
            slug = _gh("repo", "view", "--json", "nameWithOwner",
                       "--jq", ".nameWithOwner")
        except (RuntimeError, OSError):
            slug = ""
    if not slug:
        return f"open a pull request from `{branch}` into `{base}`"
    return f"https://github.com/{slug}/compare/{base}...{branch}?expand=1"


def deliver(
    invariant: str,
    level: Level,
    body: str,
    *,
    artifact_path: Path,
    pr_number: int | None = None,
    branch: str | None = None,
    commit_paths: list[Path] | None = None,
    title: str = "",
) -> ActionReceipt:
    """Deliver a workflow's output at the invariant's earned level.

    REPORT  -> write artifact_path only.
    COMMENT -> also comment on pr_number (requires a PR context).
    PROPOSE -> also commit commit_paths to `branch` and open a PR.
    ACT is deliberately unimplemented in the MVP.
    """
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(body if body.endswith("\n") else body + "\n")

    if level >= Level.COMMENT and pr_number is not None:
        _gh("pr", "comment", str(pr_number), "--body-file", str(artifact_path))
        return ActionReceipt(invariant, level, "comment", f"PR #{pr_number}")

    if level >= Level.PROPOSE and branch and commit_paths:
        base = _gh("repo", "view", "--json", "defaultBranchRef",
                   "--jq", ".defaultBranchRef.name")
        subprocess.run(["git", "checkout", "-B", branch], check=True,
                       capture_output=True, timeout=30)
        subprocess.run(["git", "add", *[str(p) for p in commit_paths]],
                       check=True, capture_output=True, timeout=30)
        ident = ["-c", "user.name=gusset[bot]",
                 "-c", "user.email=gusset@users.noreply.github.com"]
        subprocess.run(
            ["git", *ident, "commit", "-m", title or f"gusset: {invariant}"],
            check=True, capture_output=True, timeout=30,
        )
        subprocess.run(["git", "push", "-u", "origin", branch, "--force"],
                       check=True, capture_output=True, timeout=120)
        try:
            url = _gh("pr", "create", "--base", base, "--head", branch,
                      "--title", title or f"gusset: {invariant}",
                      "--body-file", str(artifact_path))
        except RuntimeError as exc:
            # GitHub disables "Allow GitHub Actions to create and approve
            # pull requests" by default, everywhere — so this is the NORMAL
            # path on a fresh install, not an exotic org policy. The work is
            # done and pushed either way; hand back a one-click compare URL
            # so opening it is a click rather than a hunt through branches.
            return ActionReceipt(
                invariant, level, "branch_pushed",
                f"{branch} pushed. Open the PR: {_compare_url(branch, base)}"
                f"\n  (GitHub blocks Actions from opening PRs by default; "
                f"this is expected. Enable 'Allow GitHub Actions to create "
                f"and approve pull requests', or give the workflow a "
                f"fine-grained PAT, to have Gusset open it for you.)"
                f"\n  refused: {str(exc)[:120]}",
            )
        return ActionReceipt(invariant, level, "propose", url)

    if level == Level.REPORT:
        return ActionReceipt(invariant, level, "artifact", str(artifact_path))
    # COMMENT/PROPOSE without their context degrades to artifact — logged.
    return ActionReceipt(
        invariant, level, "artifact",
        f"{artifact_path} (no {'PR' if level == Level.COMMENT else 'branch'} context)",
    )
