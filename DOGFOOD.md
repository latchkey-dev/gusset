# Dogfood log

Gusset develops Gusset. Every friction point, surprise, or win from using
the tool on itself lands here — this file is the product backlog the tool
earns by being used. Newest first.

## 2026-08-24 (the foreign-repo gauntlet)

First run of Gusset against a repo it was not developed on: a TypeScript
pnpm monorepo (30 files, 78 symbols, 13 packages). Everything below was
invisible on our own Python repo and obvious within an hour on someone
else's.

- **BUG→FIXED — CRITICAL: the graph fabricated edges.** The one invariant
  the whole product rests on — *never guess an edge* — was violated by the
  extractor. `_callee_name` threw away the receiver, so `router.get()`,
  `store.get()`, `request(app).get()` and `os.environ.get()` all became
  calls to a unique `CacheService.get` via a repo-wide unique-name
  fallback. **11 of 59 call edges on the foreign repo were fiction.** Then
  we measured our own repo: **430 of 1776 (24%)**. Every impact radius and
  `closure_recall` score we ever published was computed on a partly
  invented graph.

  Fix: `Ref` now carries a receiver (`None` bare · `self`/`this` · a name ·
  `?` unknown), and resolution is receiver-aware. `self.f()` searches
  enclosing class scopes outward and never repo-wide; `x.f()` resolves
  **only** through an exact import-alias match, never a prefix guess;
  anything else is counted unresolved. Verified by re-auditing every call
  edge against its own source line: foreign repo 11 → **0**, gusset 430 →
  **0**. Pinned by `tests/test_no_fabrication.py` against the real
  four-way `.get()` collision that produced it.

  The honest cost, stated plainly: unresolved refs rose 605 → 617
  (foreign) and edges fell 1776 → 1305 (ours). We did not lose
  information — we stopped inventing it, and started counting the misses.

- **Process lesson — a monoculture hides the bug that matters most.** This
  survived every test we had because our tests were written against the
  code we wrote, in one language, in one idiom. Three independent gauntlet
  agents flagged it within minutes on unfamiliar code. Dogfooding on
  yourself is necessary and *not sufficient*: it validates the paths you
  already thought of.

- **BUG→FIXED — CRITICAL: impact was blind to module-scope callers.**
  `expand_ring` skipped every dependent whose kind was `module`, so
  `gusset impact` reported **"No dependents found — the change is
  contained to the seed symbols themselves"** for the single
  most-depended-upon symbol in the foreign repo. Module scope is where
  TS/JS *lives*: route registration, test bodies, config, script
  top-level. 39 of 59 edges there originated in a module.

  Worse, the reverse closure the run is *scored* against traverses
  through module nodes, so impact was being graded on symbols it was
  structurally forbidden from reaching. Both filters removed in one
  commit — numerator and denominator have to move together or the ladder
  demotes on a scoring artifact (we have shipped that bug before). The
  same symbol now returns a correct depth-1 impact at
  `closure_recall=1.0`, annotated "(module scope)".

  Our Python fixtures never caught this because module-scope calls are
  rare in idiomatic Python. The regression test is deliberately written
  in TypeScript for that reason.

- **BUG→FIXED — TypeScript imports barely resolved at all.** 2 `imports`
  edges for a monorepo whose every file starts with imports. Three forms
  were unreadable, and not one of them was ambiguous — each is answered
  by a file already in the repo:

  | Form | Answered by |
  |---|---|
  | `./routes/incidents.js` | the compiler's rule that a `.js` specifier in TS source names the `.ts` that emits it |
  | `@/lib/api` | that project's `tsconfig.json` `paths` (with `extends` merged) |
  | `@pulse/shared` | the workspace `package.json`'s `name` and `types`/`main` |

  New `graph/tsmodules.py` reads those declarations and proposes candidate
  module qualnames; the indexer takes the first that exists and otherwise
  resolves nothing. **Import edges on that repo: 2 → 18, and all 18 were
  checked by hand against their source line and target file.** Total
  edges 55 → 71, unresolved 625 → 609. An alias is scoped to the project
  that declares it, so two packages binding `@/*` to different directories
  cannot bleed into each other.

  tsconfig is JSONC in practice, so the parser strips comments and
  trailing commas with a string-aware scanner — a regex would have eaten
  the `//` in `"https://…"`.

- **BUG→FIXED — the indexer paid for `node_modules` on every run.** Both
  walks used `rglob` and filtered afterwards, so a populated
  `node_modules` was fully enumerated twice before being discarded. Now
  pruned at the directory level: 8k skipped files went 0.31s → 0.056s,
  and real installs are far larger than that. Found while adding the
  second walk — writing the same slow thing twice is what made it
  visible.

- **BUG (open, known class) — bare cross-file calls still use a
  unique-name fallback.** `resolve()` still resolves a bare `render()`
  to a unique repo-wide `render` even when the caller never imports it.
  The receiver fix closed the large hole and the audit above only
  certifies receiver-style calls, so this class remains open and is
  stated here rather than quietly implied away. Now that import aliases
  are recorded, requiring an alias match for bare cross-file resolution
  is available — with a carve-out for Go, where package scope genuinely
  spans files.

- **BUG→FIXED — the honesty fix made deadcode lie, so refusals are now
  recorded.** Fewer fabricated edges means more symbols with no
  *resolved* caller: our dead list went 298 → 361 and included
  `GraphStore.dead_symbols` — the method that implements `gusset
  deadcode` — because it is only ever called as `store.dead_symbols()`.
  A correct refusal to guess had turned into a wrong answer downstream.

  Root cause was bookkeeping: unresolved references were *counted*, not
  kept, so no query could tell "nothing references this" from "we could
  not see the reference." They now go in an `unresolved_refs` table with
  scope, receiver, kind, line and reason, and deadcode reports two
  buckets: `dead` (no edge **and** no unresolved reference sharing the
  name — safe to act on) and `--unverified` (we can neither show a caller
  nor rule one out). Ours: 361 → **246 dead, 114 unverified**, and
  `dead_symbols` is correctly in the second bucket.

  Matching is by bare name, so a symbol called `get` is shielded by every
  unresolved `.get()` in the repo. Deliberate: this list proposes
  deletions, and a missed deletion costs nothing while a wrong one costs
  trust.

- **FINDING CORRECTED — the tool was right and the audit was wrong.** My
  own gauntlet notes recorded `getServiceStatus`, `setServiceStatus`,
  `del`, `disconnect` and `createRateLimit` as live methods that deadcode
  had falsely flagged. Grepping the source: they are never called
  anywhere in that repo. Gusset was correct and the human-written finding
  was not — logged here because an audit that is never itself audited is
  just a second opinion with better formatting.

- **BUG→FIXED — React code referenced things in three ways the graph
  could not see.** The remaining deadcode false positives were all React,
  and each had a distinct cause:

  1. **JSX usage was not a reference.** `<ServiceCard />` uses
     `ServiceCard` exactly as `ServiceCard()` would, and the extractor
     walked straight past it, so components rendered on every screen were
     unreferenced. Now extracted. `<div>` is not: JSX compiles lowercase
     tags to strings and capitalized ones to identifiers, so
     capitalization is the language's rule, not a heuristic of ours.
  2. **The module/component name collision blocked resolution.**
     `ServiceCard.tsx` produces a module named `ServiceCard` *and* a
     component named `ServiceCard`, so the unique-name fallback saw two
     candidates and gave up. Modules are now excluded as candidates for
     `calls`/`inherits`/`exports` — a module is not callable, so this is a
     type constraint, not a preference between equals.
  3. **Default exports left entry points unreferenced.** `export default
     function HomePage()` is called by the framework, not by the repo.
     Recorded now as an `exports` edge, module → symbol. Deliberately
     driven by the export statement in the source, never by a
     framework's file-path convention — inferring "this is a Next.js
     page" from a directory layout would be exactly the kind of guess
     this codebase refuses.

  Plus a parity bug the same repo surfaced: `constructor` was reported as
  dead code. It is TypeScript's `__init__` — invoked by the language,
  never by name — and Python's dunder exclusion had no TS equivalent.

  **Result on that repo: 19 dead symbols → 9, and all 9 verified by hand
  as genuinely uncalled.** Call edges 42 → 46, still zero fabricated.

## 2026-08-18 (heartbeat)

- **FEATURE — live CLI→browser sync (SSE heartbeat).** `/api/events`
  streams run events; the frontend auto-navigates to the matching tab on
  run start (with a 10s interaction-suppression window + follow toast),
  live-updates in-flight views, and refreshes the graph on index signals
  while preserving camera/selection. Real-test verified: `gusset impact`
  in a shell auto-opened the impact tab in 49ms and the view grew nodes
  live, zero reloads.
- **BUG→FIXED — watcher blind to recreated files.** File-tail offsets
  keyed on name+size went silent when a session file was deleted and
  recreated at the same byte size (hit during live verification). Offsets
  now carry the inode.
- **SSE contract refined from use:** finish events now carry the workflow
  name (the finish toast couldn't name the workflow without it). Known
  remaining gap: no Last-Event-ID replay on reconnect — the poll fallback
  covers it; candidates logged.

## 2026-08-18 (the PR-image 404 — Daniel's find)

- **BUG→FIXED — comment image 404'd on the real PR.** Two-layer design
  error: raw.githubusercontent images can never render in private-repo
  comments (GitHub's Camo proxy fetches anonymously), and the image lived
  on the PR branch, which squash-merge deletes. Root process lesson: I
  verified the comment MARKDOWN and a local render, never the rendered
  pixel on github.com itself — the last inch is where it broke. Fix is
  structural: blast diagrams are now Mermaid (native GitHub rendering,
  no hosting, no branch coupling), which also deleted the entire
  commit-SVG-and-push machinery. Existing PR #3 comment patched in place.

## 2026-08-18 (serve review round — Daniel's feedback)

- **BUG→FIXED — installed-tool staleness bit again.** The e2e video first
  recorded the drift run NOT respecting a fresh allowlist entry — the demo
  shell was running the previously installed gusset, not the working tree.
  Same class as the .env discovery bug: install-and-use catches what dev
  runs hide. The video assertion (recording must show "2 claims") now
  guards it.
- **BUG→FIXED — allowlist looked in the wrong root.** `docs-drift --repo
  docs` loaded the allowlist from under docs/, not beside the graph db.
  Allowlist now anchors to the .gusset parent.
- **UX round from real use (Daniel):** graph hairball → degree-normalized
  springs + Laplacian warm start + collision radius + label pills capped
  at 12; impact label collisions → radial placement + greedy nudge, seed
  pill always on top; drift buttons were dead UI → allowlist is now a real
  committable file the workflow respects + inline doc excerpts; every view
  gained an "ⓘ what is this?" explainer. Screenshots-as-spec worked well.

## 2026-08-18 (serve build)

- **BUG→FIXED — perfect runs scored as breaches.** The ladder recorded raw
  `gate_drop_rate` into min_score, so a flawless run (drop rate 0.0) read
  as min 0.00 — three of those would DEMOTE a perfect invariant. Invisible
  in JSONL for days; obvious the moment the serve ladder view drew the bar
  at zero height. Rate metrics now normalize lower-is-better; ledger
  recomputed. The visualization justified itself before it shipped.
- **BUG→FIXED — only impact wrote run events.** Drift and atlas commands
  never wired RunLog, so their serve views would be forever empty. Same
  class as the earlier "harness silently degraded in CI": optional layers
  need every entry point wired, not just the first one built.
- **COSMETIC (logged) — workflow view narrates atlas runs in impact
  vocabulary** ("0 seeds resolved") since turn payloads are impact-shaped.
  Needs per-workflow feed templates; honest but clumsy.
- **WIN — serve end to end on real data.** All six views, both themes,
  zero console errors across 12 scenarios, against this repo's live graph
  (726 symbols, 10 packages) and real run files.

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
