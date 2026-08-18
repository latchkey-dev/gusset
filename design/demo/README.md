# Gusset product-demo animation

A self-contained, deterministic ~4:40 choreographed product demo. 1920×1080
stage styled as a mocked desktop in the Blueprint Paper theme: a terminal
window (typed commands, real output), an app window (faithful mocks of the
`gusset serve` views), a drawn SVG cursor that guides the eye, lower-third
captions, and scene-card wipes between scenes.

No build step. No external dependencies except Google Fonts
(Archivo 400/600/800 + Spline Sans Mono 400/500). Everything else is inline.

## Files

| File | Role |
|---|---|
| `demo.html` | page shell (fonts + stylesheet + scripts) |
| `demo.css` | stage, windows, terminal, app-view mocks, cursor, captions, wipes |
| `scenes.js` | the timeline — 8 scenes of `[t_ms, action, ...args]` steps |
| `demo.js` | engine: compiles scenes into one flat event list, rAF scheduler, app-view templates |
| `assets/` | ground-truth command outputs (see provenance below) |

## Playing it

Open `demo.html` (file:// is fine) at a 1920×1080 viewport and call:

```js
window.demoPlay();      // starts (or resumes after a seek)
window.demoDuration;    // total length in ms (280000)
window.demoSeek(ms);    // rebuild the stage in the exact state at `ms`
```

Or open `demo.html?play=1` — it waits for fonts, then autoplays.

Deterministic: every run is identical; all timing is fixed offsets on a
single clock. `demoSeek(ms)` rebuilds the DOM and instant-applies every
event ≤ `ms` (CSS animations/transitions suppressed so end-states show);
`demoPlay()` resumes from the seeked time.

## Recording (Playwright sketch)

```js
const ctx = await chromium.launchPersistentContext('', {
  viewport: { width: 1920, height: 1080 },
  recordVideo: { dir: 'out/', size: { width: 1920, height: 1080 } },
});
const page = await ctx.newPage();
await page.goto('file://…/design/demo/demo.html');
await page.evaluate(() => document.fonts.ready);
await page.evaluate(() => window.demoPlay());
await page.waitForTimeout(await page.evaluate(() => window.demoDuration) + 1500);
await ctx.close(); // flushes the video
```

## Scenes

| # | Start | Length | Scene | What happens |
|---|---|---|---|---|
| 1 | 0:00 | 20 s | Cold open | logo draws itself, title card, both windows slide in |
| 2 | 0:20 | 30 s | The map | `gusset index .` → real counts; GRAPH view node field fades in |
| 3 | 0:50 | 50 s | Impact | `gusset impact --symbol serve.events.RunLog.sessions`; IMPACT view animates the run: seed, ring-1 nodes, one claim dropped at the gate, score bars |
| 4 | 1:40 | 45 s | The pull request | `git push`; app window becomes the gusset[bot] PR comment (diagram + verified bullets), cursor scrolls it |
| 5 | 2:25 | 40 s | Docs drift | `gusset docs-drift docs/` → 3 stale; allowlist click removes one; re-run shows 2 stale |
| 6 | 3:05 | 40 s | The ladder | LADDER view; deadcode-zero bar strip fills 15 runs, chip flips to COMMENT; ledger JSON in terminal |
| 7 | 3:45 | 35 s | Agents drive it | Claude-Code-style session runs `gusset impact` and summarizes; SKILL.md excerpt in app window |
| 8 | 4:20 | 20 s | Close | windows shrink to corners; logo + tagline "Autonomous self-healing repo upkeep." |

Total: **280 000 ms (4:40)**.

## Ground truth — where each scene's data comes from

| Scene | Source | Notes |
|---|---|---|
| 2 | `assets/out-index.txt` | JSON line verbatim (798 symbols, 1 521 edges, 10 packages, 2 744 unresolved) |
| 3 | `assets/pr-comment.md` | the 8 verified-impact qualnames and "calls / depth 1" edges; ring labels use the mermaid block's short names |
| 4 | `assets/pr-comment.md` | mermaid diagram structure (n0/n1 seeds → 8 pass nodes, exact edge map), Seeds line, summary opening, first three bullets, and the footer line — all verbatim; long parts trimmed with a visible "…" |
| 5 | `assets/out-drift.txt` | "wrote /tmp/dd.md — 3 claims checked, 2 stale", trace URL and `exit=2` line verbatim; reference names/line numbers from the approved ViewDrift board |
| 6 | `assets/out-ladder.jsonl` | the two `run` lines and the `level` line (reason "15 consecutive runs >= 0.9") verbatim; the other three invariant cards come from the approved ViewLadder board |
| 7 | `assets/skill-excerpt.txt` | frontmatter, one-sentence pitch, "why agents should care", and the 3-row command table verbatim |
| visual | `design/Main.dc.html`, `design/View*.dc.html`, `src/gusset/serve/static/styles.css` | tokens, layout, and component styling for the app-window mocks |

## Asset gaps / honest deviations

CLI text is verbatim from `assets/` wherever an asset exists. Where the
script demanded something the assets don't contain, the deviation is small
and listed here:

- **Scene 3 dropped claim** — `assets/pr-comment.md` records a clean run
  ("0 dropped at the gate", kept verbatim in scene 4). The scripted gate-drop
  in scene 3 uses the approved ViewImpact board's example
  (`probe.tracing.flush_all — edge not in graph`); the terminal summary line
  ("9 claims checked → 8 verified, 1 dropped") and `gate_drop_rate 0.11`
  (= 1/9) follow from that fiction. `closure_recall 1.00` / `summary_grounding
  1.00` are asserted by the approved caption script.
- **Scene 5 first run** — the asset only captures the *post-allowlist* state
  ("3 claims checked, 2 stale"). The scripted 3→2 progression shows a derived
  first run of "3 stale"; the re-run line is verbatim. The PandaProbe 429
  retry noise is cut with a visible "… telemetry retry lines trimmed …" line.
- **Scene 4 git output** — `git push` boilerplate (object counts, fake
  `4c11f2e` commit) is invented; no asset exists for it. The PR comment
  content itself is verbatim.
- **Scene 7 dialogue** — the agent conversation is written for the demo; its
  claims (read-path consumers + the two tests) are grounded in
  `assets/pr-comment.md`, and the "8 verified · 1 dropped · closure_recall
  1.00" line matches scene 3.
- **Graph view** — node positions/clusters are invented (the graph DB isn't
  in assets); sidebar filter counts are omitted rather than invented; footer
  counts are real. Package nodes (`tree_sitter`, `langgraph`) follow the
  boards. Session id `impact-6f4a10a373ef` and commit `9981aa7` come from the
  ViewImpact/ViewGraph boards.

## Verification

Two Playwright checks were used (and are easy to reproduce):

1. **Seek stills** — load the page headless at 1920×1080, `await
   document.fonts.ready`, then for each key timestamp call
   `demoSeek(ms)` and screenshot. `demoSeek(demoDuration)` doubles as a
   smoke test: it executes every compiled event once, so any bad action
   or selector throws.
2. **Real-time pass** — `demoPlay()`, wait `demoDuration + 1s`, while
   listening to `page.on('pageerror')` and `console` messages of type
   `error`, asserting **zero** of either across the full 280 s
   (screenshots taken along the way to check the animation mid-flight).

Last full pass: clean — 0 console errors, 0 page errors.
