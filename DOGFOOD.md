# Dogfood log

Gusset develops Gusset. Every friction point, surprise, or win from using
the tool on itself lands here — this file is the product backlog the tool
earns by being used. Newest first.

## 2026-08-24 (second foreign repo: production scale)

A 1,341-file production monorepo — TypeScript, Go, Terraform, four
lambda fleets — indexed in **5.5s**: 6,419 symbols, 26,741 edges, 159
packages. An order of magnitude past anything we had tried, and the
scale itself broke two things a small repo could not.

- **CORRECTION — my own fabrication audit was wrong, and the number I
  published with it.** The audit script tested `f".{name}(" in line` to
  spot a receiver-style call. In JavaScript, `...spread(x)` contains
  `.spread(` — the last dot of the ellipsis. On this repo that reported
  **231 fabricated edges**; every one was the audit's own false positive,
  and the four that survived a corrected regex turned out to be *correct*
  static calls (`ParkedRunnerStartService.isEnabled()` resolved through
  its import). So: **zero fabricated edges here.**

  Re-running the corrected audit against the pre-fix snapshot puts the
  earlier "430 of 1776 call edges (24%)" at **348 of 1776 (19.6%)**. The
  finding stands and is still enormous; the number I stated was inflated
  by my own tooling. Logged rather than quietly edited, because a project
  whose whole claim is "the graph is the oracle" does not get to be loose
  about the measurement of its own graph. The audit now requires a real
  receiver character (`[\w)\]]`) before the dot.

- **BUG→FIXED — Go test functions reported as dead code.** `go test`
  finds `TestXxx` / `BenchmarkXxx` / `ExampleXxx` / `FuzzXxx` by
  reflection; nothing in the source calls them. Exactly the category
  `main` is already excluded for, and the exclusion had no Go arm. **37
  false positives** on this repo. Dead list 389 → 352.

- **BUG→FIXED — the docs-drift anchor rule did not survive scale.**
  Yesterday's rule — drift requires *some* prefix to resolve — is
  perfect on a 78-symbol repo and leaks on a 6,419-symbol one, because
  almost any common word is a symbol name somewhere. It anchored
  `start.dateTime` (a Google Calendar API field) on a *method* named
  `start`, `poolConfig.maxCount` on a *function* named `poolConfig`, and
  `state.setEnvCalls` on a method named `state`.

  The missing constraint was a type one: **a function cannot own a dotted
  member.** Only a module or a class can. Requiring the anchor to resolve
  to a container took this repo from **22 stale to 6** — and the 6 that
  remain (`githubAppService.createWebhook`,
  `tenantContext.loadUserContext`, `organizations.self_heal_mode`) are
  genuinely worth a human's eye, which is the whole point. Verified not
  to regress: planted drift anchored on both a class and a module is
  still caught, exit 2 intact.

  Worth naming the pattern — this is the second time a rule that read as
  principled on a small repo turned out to be doing its work by
  coincidence at that size.

- **LIMITATION (open) — Go types look dead.** Of the 352 remaining, a
  large share are Go structs and interfaces (`Reservation`,
  `ReservationStore`, `reserveCacheRequest`) used as `var x T` or `T{}`.
  Type *usage* is not extracted as a reference in any language, which is
  the same family as TS interfaces being invisible. This is now the
  largest known false-positive class in deadcode.

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
  we measured our own repo: **430 of 1776 (24%)** — later corrected to
  **348 (19.6%)** when the audit script's own bug surfaced on the next
  repo; see the production-scale entry above. Every impact radius and
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

- **BUG→FIXED — docs-drift was a 100% false-positive machine, and it fed
  on itself.** First run on the foreign repo: *8 claims, 8 stale*. Fourth
  run: *32 claims, 32 stale*. Two separate bugs stacked.

  It read its own report back in. `docs-drift.md` is a markdown file full
  of backticked dotted paths, matched the default `**/*.md`, and each run
  re-harvested the previous run's findings — the growth was pure echo.
  The output file is now excluded from its own input (and the artifacts
  are gitignored).

  The deeper bug: every backticked dotted string was treated as a claim
  about our code. The eight "stale symbols" were `m6a.large` (an AWS
  instance type) and things like `self_heal_attempts.run_id` (database
  columns). Drift now requires an **anchor** — some proper prefix of the
  path must itself resolve. `store.GraphStore.gone` is drift because
  `store.GraphStore` exists and the method does not; `m6a.large` anchors
  on nothing, which is not evidence a symbol went missing, it is evidence
  the sentence was never about our code. Unanchored references are
  counted and disclosed, never reported as stale. This is the resolver's
  own rule applied to prose: absence of evidence is not evidence of
  absence.

  Turning it on ourselves then exposed a third bug, in the opposite
  direction: our eval notes write `atlas.partition` for
  `…atlas.build_atlas_graph.partition`, abbreviating an *interior* scope,
  and contiguous-suffix matching called all three stale. Matching now
  allows earlier segments to appear in order with the final segment
  exact. Deliberately a **new** store method rather than loosening the
  shared suffix matcher — that one also backs the serve lookup, and
  relaxing a shared primitive to fix a report is how a scoring change
  sneaks in through the side door.

  **Foreign repo 32 stale → 0. This repo 7 stale → 0, 39 references
  verified.** And a planted `store.GraphStore.completely_invented_method`
  is still caught, which is the assertion that keeps this a check rather
  than a mute button.

- **BUG→FIXED — every run looked like it was erroring.** On a free
  PandaProbe tier the SDK logged four to eight
  `429, retrying in 0.5s` warnings per run. Tracing is optional and
  scores are local, so nothing was actually wrong — but that is not what
  a stranger's first run looks like. The SDK uses `logging`, so the
  retries are now collapsed by a filter into one line naming the count
  and stating that scores are unaffected. The ERROR when retries are
  exhausted still prints: suppressing the chatter is a courtesy,
  suppressing the outcome would be a lie about whether the trace exists.

- **BUG→FIXED — monorepo manifests were one level out of reach.**
  `parse_manifests` scanned the root and one level down. A pnpm workspace
  keeps its manifests at `apps/api/package.json` and
  `packages/shared/package.json` — two levels — so on the foreign repo
  **all four workspace manifests were invisible**, and `express` (×6),
  `@prisma/client` (×4), `zod`, `next` and `ioredis` resolved to nothing
  despite being declared right there. Now walks the whole repo (pruned),
  shallowest first so the root manifest still wins a version collision.
  **Packages 13 → 40, external import edges 3 → 25, unresolved 609 →
  587**, and all 25 checked by hand against their specifier.

  Caught only because the advisor asked why `imports_external` had not
  moved all session. It had been sitting at 3 through every re-index, and
  I had read past it each time — the number was on screen a dozen times
  and never once questioned.

- **BUG→FIXED — the one file we tell users to curate was gitignored.**
  Adding entries to `.gusset/drift-allowlist.txt` revealed that
  `.gitignore` excluded all of `.gusset/`. So the allowlist never reached
  CI: a user curates it locally, the custodian's next run re-flags every
  entry, and the serve UI's one-click "allowlist this" button writes to a
  file that is never committed. The docs said "safe to edit" about a file
  the repo was configured to throw away.

  Fixed as `.gusset/*` plus `!.gusset/drift-allowlist.txt` — git cannot
  re-include a path whose parent *directory* is excluded, only one whose
  *contents* are, so the trailing-slash form silently defeats the
  negation.

- **WIN (and a joke at our expense) — the drift checker caught its own
  documentation.** Writing up the anchor rule meant putting
  `store.GraphStore.gone` in three files as an *example* of a missing
  symbol. It is, in fact, a missing symbol, so docs-drift dutifully
  reported three drifts and exited 2. The allowlist is the designed
  answer and it worked, but the lesson generalizes: prose *about* a
  checker is still input *to* that checker.

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
