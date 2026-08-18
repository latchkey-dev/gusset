# Gusset workflows — flags, outputs, failure modes

All commands: `--db` (default `.gusset/graph.db`). LLM commands read
`.env` from the working directory upward.

## gusset index REPO
Deterministic, no LLM. Rebuilds the graph. Output JSON: files, symbols,
edges, packages, imports_external, unresolved_refs. Re-run after big
changes; the graph records its commit.

## gusset impact
Seeds: `--symbol <qualname>` (repeatable) and/or `--diff <git-range>`
(changed lines → overlapping symbols; on a PR use
`origin/<base>...HEAD`). `--yes` waives the approval gate. `--model` /
`GUSSET_MODEL` override (default claude-opus-5, fallback tier
claude-sonnet-5 automatic). Writes `--out` (default impact-report.md).
Failure modes: exit 1 "No seeds" = nothing in the diff touched indexed
symbols (doc-only change, or index is stale — re-index); halted = seed
not in graph (typo, or symbol is new and unindexed).

## gusset atlas
No seeds. Produces architecture doc with Mermaid whose edges are
graph-computed. Modules = top-level directories. Scores:
module_coverage, gate_drop_rate, summary_grounding.

## gusset deadcode
Pure query. Conservative: excludes dunders, `main`, packages. Dynamic
dispatch can make live code look dead — present results as candidates,
not verdicts.

## gusset docs-drift
`--repo <dir>` scopes which docs are scanned; the allowlist always loads
from the .gusset root. `--no-llm` = fully deterministic. Exit 2 = drift.
Stale ≠ wrong: stdlib/API mentions belong in `.gusset/drift-allowlist.txt`
(the serve UI has a one-click button for this).

## gusset run-event
CI entry point (the Action calls it). Triggers: pull_request | push |
cron | manual. Prints one receipt per invariant: ran (with scores and the
delivered action), skipped (with the guard that stopped it), errored
(provider weather — not ladder-scored). Humans rarely run this directly.

## gusset serve
Localhost UI: graph explorer, impact replay, live workflow feed, drift
map with allowlist buttons, autonomy ladder, setup. Read-only for LLM
runs — it shows the command to copy instead of running models itself.
