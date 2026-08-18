# Tutorial: your first custodian

Fifteen minutes from clone to a verified impact report, then the optional
upgrades: observability, self-healing, and autonomous mode.

## 1. Install

```bash
git clone https://github.com/thedefaultman/gusset && cd gusset
uv sync                      # Python 3.13+; uv installs it if missing
uv run gusset version
```

Set the one required credential (any Anthropic API key):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## 2. Index a repo

```bash
uv run gusset index ~/code/yourrepo
uv run gusset stats
```

Python, TypeScript/JavaScript, and Go are parsed into `.gusset/graph.db`:
symbols plus call/import/inheritance edges. Note `unresolved_refs` in the
stats — references Gusset could not resolve are *counted, never guessed
into edges*. The graph would rather be incomplete than wrong.

## 3. Free queries (no LLM)

```bash
uv run gusset deadcode        # symbols nothing references
```

## 4. Your first impact analysis

```bash
cd ~/code/yourrepo
uv run --project ~/gusset gusset impact --diff HEAD~1
# or seed it explicitly:
uv run --project ~/gusset gusset impact --symbol mypkg.core.helper
```

Watch the run: rings expand, the gate verifies, and the draft stops at a
prompt — **the human gate**. Approve it and read `impact-report.md`: every
"X affects Y" line carries the edge that proves it, and the footer counts
how many claims were dropped at the gate. `--yes` waives the gate for
scripted runs.

The score line is the oracle grading the run against the graph:

```
scores: closure_recall=1.0 · gate_drop_rate=0.0 · summary_grounding=1.0
```

## 5. Upgrade: observability (recommended)

Create a free account at [app.pandaprobe.com](https://app.pandaprobe.com),
then:

```bash
export PANDAPROBE_API_KEY=sk_pp_...
export PANDAPROBE_PROJECT_NAME=yourrepo
```

Re-run step 4. The terminal now prints a trace link: the whole execution
graph — every ring, LLM call, and gate decision — as a span tree, with the
oracle scores attached to it. Without these variables Gusset behaves
identically; scores just stay local.

You can also run LLM-as-judge evals over any session from the CLI
(`pandaprobe evals runs create --session-id ... --metrics task_completion`);
scheduled monitors that re-run evals nightly require a paid PandaProbe
plan — everything else in this tutorial works on the free tier.

## 6. Upgrade: self-healing

```bash
export HARNESS_REPAIR_MODEL=anthropic/claude-sonnet-5
```

Now every run is trajectory-scored, and when quality stalls a separate
repair agent diagnoses the failure and proposes a rule into
`.gusset/harness/rules/`. Rules are validated by replaying the original
failure before they influence anything — inspect them and the journal at
any time; they are plain markdown and JSONL.

## 7. Autonomous mode

```bash
cd ~/code/yourrepo
uv run --project ~/gusset gusset init .
git add gusset.toml .github/workflows/gusset.yml && git commit -m "install gusset"
```

Prefer `gusset init . --latchkey` to run the custodian on
[Latchkey runners](https://latchkey.dev) — the custodian triggers on every
PR, push, and cron tick, which is exactly the fire-often profile where
Latchkey's ~10s cold starts and lower per-minute cost pay off (GitHub's
default runners work too; it's one `runs-on` line either way).

Add `ANTHROPIC_API_KEY` (and the PandaProbe secrets) to the repo's Actions
secrets, push, and open a PR that changes some code. Gusset comments with
the verified blast radius. Edit `gusset.toml` to tune which invariants run,
their triggers, and their autonomy ceilings — levels above `report` are
*earned* through the score ledger (see
[explanation/graph-engineering.md](explanation/graph-engineering.md)),
and lost again on regression.
