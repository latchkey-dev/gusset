# CLI reference

All commands read `.env` (via python-dotenv) for credentials. The graph
database defaults to `.gusset/graph.db`.

## `gusset index REPO [--db PATH]`

Parse a repository (Python, TypeScript/JS/JSX, Go) into the graph
database. Replaces any prior index. Output: JSON counts including
`unresolved_refs` — references that could not be resolved and were
recorded as such, never guessed.

Edge kinds: `calls`, `imports`, `inherits`, `imports_external`, and
`exports` (a module to its default-exported symbol — a Next.js page or
React component is referenced by the framework, not by the repo, and
without that edge it reads as dead code). JSX element usage counts as a
reference: `<ServiceCard />` uses `ServiceCard` exactly as
`ServiceCard()` would. Lowercase tags are intrinsic DOM elements and are
not symbols.

Call resolution is receiver-aware and deliberately incomplete. A bare
`f()` resolves through the enclosing scopes and then a unique repo-wide
name; `self.f()` / `this.f()` resolves inside the enclosing class only;
`x.f()` resolves **only** through an exact import alias, because the type
of `x` is not knowable to a parser. Anything else is left unresolved
rather than guessed — a wrong edge would poison every claim the oracle
verifies.

## `gusset stats [--db PATH]`

Graph statistics: files, symbols by kind, edges by kind, index metadata
(root, git commit, unresolved count).

## `gusset deadcode [--db PATH] [--unverified]`

Deletion candidates as JSON. Pure query — no LLM, no credentials.
Conservative exclusions: modules, packages, dunders, `main`.

A symbol is reported dead only when **no reference of any kind reaches
it**: no edge in the graph, and no reference anywhere that failed to
resolve against its name. That second condition matters because the
resolver never guesses. A method called only as `store.flush()` produces
no edge — the type of `store` is unknowable to a parser — and treating
that absence as death would turn a correct refusal into a wrong answer.

`--unverified` adds the middle bucket, output becoming
`{"dead": [...], "unverified": [...]}`. Entries there are unreferenced
symbols whose name appears in at least one unresolved reference
(`unresolved_refs_sharing_name` counts them): the graph can neither show
a caller nor rule one out. Expect dynamic dispatch, framework
registration, and calls through local variables here.

Matching is by bare name, so a symbol named `get` is shielded by every
unresolved `.get()` in the repo. That is deliberate. `dead` is meant to
be safe to act on, and in that trade a missed deletion costs nothing
while a wrong one costs trust.

## `gusset impact [--symbol Q]... [--diff RANGE] [--db PATH] [--out FILE] [--yes] [--model M]`

Verified blast radius. Seeds come from `--symbol` (exact qualnames) and/or
`--diff` (a git range; changed lines map to overlapping symbols). Exit 1 on
no seeds or a rejected draft. `--yes` waives the interactive human gate.

Requires `ANTHROPIC_API_KEY`. Prints oracle scores after the run:
`closure_recall`, `closure_confidence`, `gate_drop_rate`, `summary_grounding`.

## `gusset atlas [--db PATH] [--out FILE] [--yes] [--model M]`

Architecture atlas: module map with verified summaries and a Mermaid
diagram whose edges are computed from the graph (never from model prose).
Scores: `module_coverage`, `gate_drop_rate`, `summary_grounding`.

## `gusset docs-drift [--docs GLOB] [--repo PATH] [--db PATH] [--out FILE] [--yes] [--no-llm]`

Check backticked dotted symbol references in docs against the graph.
Deterministic core; the LLM writes only an optional explanation paragraph
(skipped with `--no-llm` or when no key is set). **Exit 2 when drift is
found** — usable directly as a CI check.

A reference is reported stale only if it is **anchored**: some proper
prefix of it must itself resolve. `store.GraphStore.gone` is drift
because `store.GraphStore` exists and the method does not. `m6a.large`
and `users.created_at` anchor on nothing — they are prose about an
instance type and a database column, not symbols that went missing — so
they are counted and disclosed in the report rather than reported as
drift. Without that rule a first run on a normal repo reports 100%
drift, which teaches the reader to ignore the tool.

Resolution allows the abbreviations docs actually use: the final segment
must match a symbol name exactly, and earlier segments must appear in
order within its qualname, so `atlas.partition` resolves to
`…atlas.build_atlas_graph.partition`.

Vendor directories (`.venv`, `node_modules`, …) are always skipped,
file-extension mentions (`config.toml`, `graph.db`) are not symbol
claims, and the report file is never read back as input — it is itself
full of backticked paths, and reading it compounded its own findings on
every run. Curate genuine externals in `.gusset/drift-allowlist.txt`.

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

# GitHub access model

Gusset never asks for, stores, or manages a GitHub credential of its own.
Delivery (comments, PRs) goes through the `gh` CLI, which resolves auth
from its environment:

- **In Actions (autonomous mode):** the generated workflow sets
  `GH_TOKEN: ${{ github.token }}` — the ephemeral installation token
  GitHub mints per run, scoped to the one repo and to the permissions the
  workflow file declares (`contents: write`, `pull-requests: write`).
  Committing the workflow file *is* the consent step: the permission block
  is visible in the diff you review when installing Gusset. The token
  expires when the job ends.
- **Locally:** `run-event` rides your existing `gh auth login` session.
  With no session, delivery degrades to an artifact file and the receipt
  says so — never a silent failure, never a credential prompt.

Two caveats to plan around:

1. **Fork PRs get a read-only token.** GitHub restricts `pull_request`
   runs triggered from forks, so Gusset cannot comment on external
   contributors' PRs out of the box — those runs deliver as artifacts.
   The usual escalations (`pull_request_target`, a GitHub App
   installation) have real security implications and are deliberately not
   the default; adopt them only with a considered threat model.
2. **By default GitHub will not let Gusset open the PR — expect this.**
   "Allow GitHub Actions to create and approve pull requests" is
   **disabled by default** on every new repository and organization, and
   most people never change it. So on a fresh install, `propose` level
   pushes the branch and receipts `branch_pushed` with a one-click
   compare URL, rather than opening the pull request itself. Nothing
   failed; the work is done and waiting for you to click.

   The checkbox governs *create* and *approve* together, and approve is
   the reason it is off: a workflow that could approve its own pull
   request could satisfy a "requires review" branch protection rule with
   no human involved. Leaving it off is a sound default.

   Two ways to have Gusset open PRs itself, if you want that:

   - **Enable the setting** (Settings → Actions → General; the org level
     overrides the repo level). Simple, but it grants the ability to
     *every* workflow in that org.
   - **Give the workflow its own token** — a fine-grained PAT or GitHub
     App token scoped to this one repository with `contents: write` and
     `pull_requests: write`, set as `GH_TOKEN` in
     `.github/workflows/gusset.yml`. Narrower, and it also fixes caveat 3
     below. Treat it as a real permissions decision either way.
3. **PRs Gusset opens do not trigger your other workflows.** Events
   caused by `github.token` never start new workflow runs (GitHub's
   anti-recursion rule), so CI will not auto-run on a Gusset-proposed PR
   (atlas refresh, dead-code removal). Re-run checks manually, close and
   reopen the PR, or — if you want them fully automatic — provide a
   fine-grained PAT or GitHub App token as the workflow's `GH_TOKEN`
   instead. Treat that as a real permissions decision: it lets a
   custodian's PRs set off everything else.

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
| `closure_confidence` | impact | resolved references ÷ (resolved + unresolved references naming the seed neighbourhood). Answers a question `closure_recall` cannot: the closure is built from resolved edges only, so a symbol whose callers were mostly unresolvable yields a tiny closure, a run that finds all of it, and a recall of 1.0 on a neighbourhood the graph is blind to. Deliberately seed-adjacent — repo-wide unresolved density would penalise ordinary Python, where stdlib and dynamic dispatch are legitimately unresolvable |
| `gate_drop_rate` | impact, atlas | claims dropped at the verification gate ÷ claims that reached it |
| `summary_grounding` | impact, atlas | backticked dotted paths in the draft that resolve in the graph ÷ all mentioned. Abbreviated paths resolve at dot boundaries |
| `module_coverage` | atlas | graph module clusters with a verified section ÷ all clusters |

All scores are computed by deterministic code against the graph — no LLM
judges, no human labels. They are pushed to PandaProbe when credentials
exist and always printed locally.
