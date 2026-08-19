# Gusset — development guide

Gusset develops Gusset. This repo is its own first customer: the custodian
runs on our PRs (see `gusset.toml`), and the dev loop below is mandatory
for humans and agents alike — every workflow pain point found here is a
product bug worth fixing.

## The dev loop

1. **Before changing shared code**, ask Gusset for the blast radius:
   ```bash
   gusset index . --db .gusset/graph.db
   gusset impact --symbol <qualname> --db .gusset/graph.db --yes
   # or after editing:  gusset impact --diff HEAD --db .gusset/graph.db --yes
   ```
   Use the verified impact list as the checklist of call sites to update.
2. **Test locally**: `uv run pytest -q` — no green, no commit.
3. **Verify on a clean machine** (catches deps/caching assumptions your
   working tree hides) before pushing anything substantial:
   ```bash
   latchkey run --timeout 900 'curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; export PATH=$HOME/.local/bin:$PATH; uv sync -q; uv run pytest -q'
   ```
4. **Push and let the custodian review**: the Gusset Action comments the
   blast radius on the PR; CI runs on Latchkey runners (`latchkey-small`).
5. **If CI fails and self-heal couldn't fix it**: the Latchkey MCP server
   (setup: docs/howto/autonomous-stack.md) exposes `list_failed_runs` /
   `get_failure_bundle` for triage, `dispatch_workflow` to re-fire, and
   `run_job` for ad-hoc clean-runner commands.

## House rules

- The graph is the oracle: never let a workflow treat model output as
  truth. New workflows follow `docs/howto/write-a-workflow.md` and the
  8-point checklist in `docs/explanation/graph-engineering.md`.
- `probe/` is the only module allowed to import pandaprobe; everything
  degrades to off without credentials.
- No LLM code in `oracle/` or `graph/`, ever.
- `evals/` results are append-only history — rerun, don't rewrite.
- Every friction point in this loop goes in `DOGFOOD.md` — it is the
  product backlog the tool earns by being used, and it is public: write
  entries as honestly as if a stranger will read them, because one will.

## Quick commands

```bash
uv run pytest -q                       # full suite
gusset deadcode --db .gusset/graph.db  # anything unreferenced?
gusset docs-drift --repo docs --db .gusset/graph.db --yes --no-llm
uv tool install --force .              # refresh the installed gusset
```
