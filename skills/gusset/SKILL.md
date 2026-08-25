---
name: gusset
description: >
  Drive Gusset, the repo custodian: index a repository into a verified code
  graph, run blast-radius impact analysis before changes, keep architecture
  docs fresh, find dead code and stale doc references, and install the
  autonomous mode that reviews PRs. Use when the user asks what a change
  affects, wants architecture/onboarding docs, asks about dead code or doc
  drift, or wants Gusset set up on a repo.
---

# Gusset — for coding agents

Gusset in one sentence: **it maintains a graph of provable facts about a
repository (every symbol, every call/import/inheritance edge, every
package) and runs workflows whose every claim is verified against that
graph before you see it.**

Why you (an agent) should care: Gusset's outputs are *trustworthy inputs
for your own work*. A Gusset impact report is a verified checklist of call
sites your edit affects — use it instead of grepping and guessing. Its
scores tell you when NOT to trust a run (see Interpreting output).

## When to reach for it

| User intent | Command |
|---|---|
| "What does changing X break/affect?" | `gusset impact --symbol <qualname>` or `--diff <git-range>` |
| "What does this PR touch?" (before you edit further) | `gusset impact --diff origin/main...HEAD` |
| "Document the architecture" / onboarding docs | `gusset atlas` |
| "Any dead code?" | `gusset deadcode` (no LLM, free; add `--unverified` for the can't-tell bucket) |
| "Are the docs stale?" / CI doc check | `gusset docs-drift` (exit 2 = drift found) |
| "Set Gusset up on this repo" | `gusset init .` (see references/setup.md) |
| "Show me the graph / the runs" | `gusset serve` (opens localhost UI) |

Every command needs an index first: `gusset index <repo>` (fast,
deterministic, no LLM). Re-index after significant changes — the graph is
a snapshot pinned to a commit.

## The three rules that make output trustworthy

1. **The graph never guesses.** References it cannot resolve are counted
   (`unresolved_refs` in stats) but never invented as edges. If a symbol
   is not in an impact report, it is either genuinely unaffected or
   unreachable through *static* edges — dynamic dispatch (registries,
   decorators, string-keyed handlers) is invisible; say so when the user's
   code is dynamic-heavy.
2. **The model writes wording; the graph owns truth.** In impact/atlas
   output, WHICH symbols appear is decided by graph traversal and
   re-verified at a gate; the LLM only wrote WHY-sentences. Claims that
   failed verification are listed as dropped, never silently kept.
3. **Every run is scored deterministically** (no LLM judge). Read the
   scores line before using a report — see Interpreting output.

## Interpreting output

`impact` prints: `scores: closure_recall=1.0 · gate_drop_rate=0.0 ·
summary_grounding=1.0`

- `closure_confidence < 0.9` — the graph could not see most of what points
  at the seed, so a high `closure_recall` means little here. Say so when you
  report the result; do not present the impact list as complete.
- `closure_recall < 1.0` — the workflow missed reachable symbols; re-run
  or fall back to reading the graph directly (`gusset stats`, serve UI).
- `gate_drop_rate > 0` — the model made claims the graph rejected; the
  report is still trustworthy (drops were removed) but note the model was
  reaching.
- `summary_grounding < 1.0` — prose mentions symbols that don't resolve;
  treat the summary paragraph skeptically, trust the verified list.
- Exit codes: `impact`/`atlas` 0 = approved report written, 1 = halted or
  rejected; `docs-drift` 2 = drift found (usable directly as a CI check).

Reports embed evidence: every "X affects Y" line names its edge kind and
depth. You can hand the verified-impacts list straight to your own editing
plan as the set of call sites to update and test.

What an absence means. The graph never guesses an edge, so "no result" is
two different answers and you should not merge them when reporting to a
user. `deadcode` splits them for you: `dead` is a finding, `--unverified`
is an unknown. `docs-drift` does the same — a dotted path nothing in the
graph corroborates is reported as "not about this codebase", not as
stale. A large `unresolved_refs` count is the same honesty, not a defect:
`x.f()` resolves only through an exact import alias, because the type of
`x` is not knowable to a parser.

## Autonomous mode (the custodian)

`gusset init <repo>` writes `gusset.toml` (which jobs run on which
triggers, at what permission level) and a GitHub Action. After the user
adds `ANTHROPIC_API_KEY` as a repo secret: every PR gets a verified
blast-radius comment with an image; architecture docs and dead-code
cleanups arrive as a pushed branch with a link to open the PR (GitHub
disables Actions-opened PRs by default — say so rather than calling it a
failure), or as the PR itself if that setting is on. Permission levels are EARNED via score history
(report → comment → propose; `act` is human-granted only) — never edit
`.gusset/ladder.jsonl` by hand; change ceilings in `gusset.toml`.

Read references/setup.md before running init for a user — it covers
secrets, runner choice (Latchkey recommended), fork-PR limits, and the
anti-recursion caveat for Gusset-opened PRs.

## Files Gusset owns (don't hand-edit)

`.gusset/graph.db` (the graph), `.gusset/runs/` (run event logs),
`.gusset/ladder.jsonl` (autonomy ledger), `.gusset/harness/` (learned
rules, if self-healing is on). Safe to edit: `gusset.toml`,
`.gusset/drift-allowlist.txt` (one dotted path per line — externals that
docs legitimately mention; add stdlib/API names here instead of "fixing"
docs).

## References

- references/setup.md — installing on a repo, secrets, CI, autonomy config
- references/workflows.md — each command's flags, outputs, and failure modes
- Full docs: docs/ in the Gusset repo (tutorial, reference, explanations)
