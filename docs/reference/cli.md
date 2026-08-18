# CLI reference

All commands read `.env` (via python-dotenv) for credentials. The graph
database defaults to `.gusset/graph.db`.

## `gusset index REPO [--db PATH]`

Parse a repository (Python, TypeScript/JS, Go) into the graph database.
Replaces any prior index. Output: JSON counts including `unresolved_refs` —
references that could not be resolved and were counted, never guessed.

## `gusset stats [--db PATH]`

Graph statistics: files, symbols by kind, edges by kind, index metadata
(root, git commit, unresolved count).

## `gusset deadcode [--db PATH]`

Symbols with no incoming edges, as JSON. Pure query — no LLM, no
credentials. Conservative exclusions: modules, dunders, `main`.

## `gusset impact [--symbol Q]... [--diff RANGE] [--db PATH] [--out FILE] [--yes] [--model M]`

Verified blast radius. Seeds come from `--symbol` (exact qualnames) and/or
`--diff` (a git range; changed lines map to overlapping symbols). Exit 1 on
no seeds or a rejected draft. `--yes` waives the interactive human gate.

Requires `ANTHROPIC_API_KEY`. Prints oracle scores after the run:
`closure_recall`, `gate_drop_rate`, `summary_grounding`.

## `gusset atlas [--db PATH] [--out FILE] [--yes] [--model M]`

Architecture atlas: module map with verified summaries and a Mermaid
diagram whose edges are computed from the graph (never from model prose).
Scores: `module_coverage`, `gate_drop_rate`, `summary_grounding`.

## `gusset docs-drift [--docs GLOB] [--repo PATH] [--db PATH] [--out FILE] [--yes] [--no-llm]`

Check backticked dotted symbol references in docs against the graph.
Deterministic core; the LLM writes only an optional explanation paragraph
(skipped with `--no-llm` or when no key is set). **Exit 2 when drift is
found** — usable directly as a CI check. Vendor directories
(`.venv`, `node_modules`, …) are always skipped; file-extension mentions
(`config.toml`) are not treated as symbol claims.

## `gusset init [REPO]`

Install autonomous mode: writes `gusset.toml` (invariant declarations) and
`.github/workflows/gusset.yml`. Refuses to overwrite an existing config.

## `gusset run-event TRIGGER [--pr N] [--diff RANGE] [--repo PATH] [--db PATH] [--config PATH]`

The supervisor entry point the GitHub Action calls. Re-indexes the repo,
routes the event through the invariants subscribed to TRIGGER
(`pull_request` | `push` | `cron` | `manual`), and prints one receipt per
invariant: `ran` with scores and the delivered action, or `skipped` with
the guard that stopped it. Nothing is ever skipped silently.

## `gusset version`

Print the version.

# gusset.toml reference

```toml
[invariants.NAME]
workflow = "impact" | "atlas" | "deadcode" | "docs-drift"
trigger  = "pull_request" | "push" | "cron" | "manual"
autonomy     = "report" | "comment" | "propose" | "act"   # current level
max_autonomy = "report" | "comment" | "propose" | "act"   # human-granted ceiling
min_changed_symbols = 1   # impact guard: skip if the diff touches fewer
```

`autonomy` must not exceed `max_autonomy` (load error). The ladder raises
the effective level only after 15 consecutive runs with all oracle scores
≥ 0.9, lowers it when 3 of the last 5 runs have any score < 0.8, and never
raises to `act` — that is a human decision expressed in config. Level
history lives in `.gusset/ladder.jsonl`, one auditable JSON line per run
and per level change.

# Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | for LLM workflows | impact/atlas explanations and synthesis |
| `GUSSET_MODEL` | no (default `claude-opus-5`) | workflow model override |
| `PANDAPROBE_API_KEY` | no | tracing + score push; absent → fully local |
| `PANDAPROBE_PROJECT_NAME` | with the key | PandaProbe project |
| `HARNESS_REPAIR_MODEL` | no | enables self-healing (e.g. `anthropic/claude-sonnet-5`) |
| `HARNESS_ROOT` | no (default `.gusset/harness`) | harness workspace location |

# Oracle scores reference

| Score | Workflow | Definition |
|---|---|---|
| `closure_recall` | impact | verified impacts ÷ the graph's reverse closure of the seeds (depth-capped). 1.0 = nothing reachable was missed |
| `gate_drop_rate` | impact, atlas | claims dropped at the verification gate ÷ claims that reached it |
| `summary_grounding` | impact, atlas | backticked dotted paths in the draft that resolve in the graph ÷ all mentioned. Abbreviated paths resolve at dot boundaries |
| `module_coverage` | atlas | graph module clusters with a verified section ÷ all clusters |

All scores are computed by deterministic code against the graph — no LLM
judges, no human labels. They are pushed to PandaProbe when credentials
exist and always printed locally.
