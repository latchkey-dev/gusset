# Dogfood log

Gusset develops Gusset. Every friction point, surprise, or win from using
the tool on itself lands here — this file is the product backlog the tool
earns by being used. Newest first.

## 2026-08-18

- **BUG→FIXED — tier-scoped 529 storms defeat retries; fallback tier added.**
  Dogfooding `gusset impact` on gusset itself during a live incident: Opus
  529'd for 20+ minutes (outlasting 8 retries) while Sonnet answered
  instantly. `make_model` now wraps the primary in `with_fallbacks` —
  capacity incidents are often tier-scoped, so change tiers instead of
  retrying into the same wall. Verified live: the same run that failed on
  retries-only completed via fallback mid-storm.
- **BUG→FIXED — installed tool couldn't find .env.** `load_dotenv()` inside
  the uv-tool-installed gusset doesn't inherit the dev-checkout context;
  now `find_dotenv(usecwd=True)` at every CLI entry. Worked in dev, failed
  installed — exactly the class of bug only install-and-use finds.
- **WIN — clean-runner verification works end to end.** `latchkey run`
  packed this repo, ran the full suite on a fresh runner: 85 passed in
  8.13s (job `cli-39b49443`). The uv bootstrap one-liner belongs in a
  snippet, though — typing it each time is friction. *(idea: `gusset
  verify` wrapping latchkey run with the right bootstrap?)*
- **BUG→FIXED — provider weather killed autonomous runs.** Two custodian
  runs died on 529 bursts. Fixes: `llm.make_model` (8 retries), errored
  receipts that don't poison the ladder, pandaprobe CLI in the Action.
  Found only because the custodian actually runs on this repo's pushes.
- **BUG→FIXED — oracle punished docs-style abbreviations.** Live PR #1
  comment scored `summary_grounding=0.56` for writing
  `atlas.build_atlas_graph.summarize_module` instead of the full
  `src.gusset.workflows...` path. Suffix-at-dot-boundary resolution added.
- **BUG→FIXED — docs-drift ate vendor dirs and filenames.** First self-run
  flagged 177 "stale" refs — mostly `.venv` READMEs and `config.toml`-style
  file mentions. SKIP_DIRS + extension filter added. It then found one real
  drift: a fabricated example path in our own explanation doc.
- **OBSERVATION — self-heal sidecar and Gusset's own resilience layer
  compose.** On the 529 failures, Latchkey's sidecar diagnosed (correctly
  not "fixing" an upstream outage) while Gusset's errored-receipt path now
  absorbs the same class. Two layers, no fight over jurisdiction.
- **LIMITATION (known, by design) — the graph can't see dynamic dispatch.**
  `unresolved_refs: 1414` on this repo (typer decorators, langgraph node
  registration). The conservative choice is right for the oracle, but a
  fan-out through `add_node("name", fn)` is invisible to impact analysis.
  Candidate future work: framework-aware edge extractors.

## 2026-08-17

- **WIN — the harness caught a real design flaw on day one.** Its first
  learned rule ("don't stop traversal after depth 1") was actually a
  *phantom lesson* caused by our verifier scoring mid-run turns as
  outcomes. The rule was wrong; the loop that produced it worked; the
  verifier now only scores synthesis turns. Exactly the kind of bug only
  live self-healing surfaces.
