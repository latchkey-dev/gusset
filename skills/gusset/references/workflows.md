# Gusset workflows — flags, outputs, failure modes

All commands: `--db` (default `.gusset/graph.db`). LLM commands read
`.env` from the working directory upward.

## gusset index REPO
Deterministic, no LLM. Rebuilds the graph. Output JSON: files, symbols,
edges, packages, imports_external, unresolved_refs. Re-run after big
changes; the graph records its commit. Edge kinds: calls, imports,
inherits, imports_external, exports (module -> its default export —
framework entry points are referenced from outside the repo). JSX
element usage is a reference; lowercase tags are DOM, not symbols.
`unresolved_refs` counts references deliberately NOT guessed at: a
qualified call like `x.f()` resolves only through an exact import alias,
so a high count is honesty, not failure.

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
Pure query. Conservative: excludes modules, packages, dunders, `main`,
`constructor`. Two buckets, and the distinction matters when you report
back to a user: `dead` means no edge AND no unresolved reference shares
the name — safe to act on. `--unverified` adds symbols the graph can
neither show a caller for nor rule one out (dynamic dispatch, calls
through a local variable): output becomes
`{"dead": [...], "unverified": [...]}`. Present `dead` as candidates,
never `unverified` — those are unknowns, not findings.

## gusset docs-drift
`--repo <dir>` scopes which docs are scanned; the allowlist always loads
from the .gusset root. `--no-llm` = fully deterministic. Exit 2 = drift.
Drift requires an ANCHOR: some prefix of the dotted path must itself
resolve, so `store.GraphStore.gone` is drift while `m6a.large` or
`users.created_at` are reported as "not about this codebase" rather than
stale. The report file is never re-read as input. Stale != wrong:
genuine externals belong in `.gusset/drift-allowlist.txt` (the serve UI
has a one-click button for this).

## gusset run-event
CI entry point (the Action calls it). Triggers: pull_request | push |
cron | manual. Prints one receipt per invariant: ran (with scores and the
delivered action), skipped (with the guard that stopped it), errored
(provider weather — not ladder-scored). Humans rarely run this directly.

## gusset serve
Localhost UI: graph explorer, impact replay, live workflow feed, drift
map with allowlist buttons, autonomy ladder, setup. Read-only for LLM
runs — it shows the command to copy instead of running models itself.
