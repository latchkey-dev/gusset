# Claude Design handoff — Scene 6: "Autonomous mode"

One scene, to be built in Claude Design. It **replaces scene 6 of the
Gusset product demo** (the current "Agents drive it" / ladder position —
slot it where the demo's flow reaches autonomy, after Drift). Target
length ~75–90 s. Everything below is self-contained; no other files
needed, but `design/demo/demo.html` shows the established stage language
if reference helps.

## Stage & design system

1920×1080. Paper theme throughout:

| Token | Value | Use |
|---|---|---|
| ground | `#F4F1EA` + dot grid (`radial-gradient(#D9D3C4 1px, transparent 1px)`, 24px) | stage background |
| panel | `#FDFCF8` | window bodies, pills |
| ink | `#22211D` | text, 1.5px window borders |
| line | `#D9D3C4` | hard offset shadows `3px 3px 0` |
| rust | `#B4551E` | accents, seed, active |
| pass green | `#2E7D4F` | success, checkmarks |
| drop red | `#C23934` | failures |
| muted | `#6B675C` / faint `#8A8577` | secondary text |
| terminal | bg `#14130F`, text `#EDE8DB` | dark panes |
| Claude coral | `#D97757` | Claude Code accents ONLY |

Fonts: **Archivo** 400/600/800 (UI, captions), **Spline Sans Mono**
400/500 (all terminal/code/qualnames). Gusset logo = three concentric
circles: rust filled dot, ink ring, dashed `#8A8577` outer ring.

Stage furniture (consistent with the rest of the demo): slim top bar
(logo + "GUSSET · PRODUCT DEMO" left, "06 — Autonomous mode" right);
lower-third caption bar (panel bg, ink border, offset shadow, Archivo 600
~20px, one sentence at a time); an SVG arrow cursor that moves along
paths and pulses a ring on click. Scene opens with the standard 1.2s
wipe + numbered title card: **"06 — AUTONOMOUS MODE"**.

## Windows

- LEFT (~46% width): **Claude Code session** — dark terminal pane styled
  after the Claude Code TUI: rounded input box at the bottom with `> `
  prompt; a coral `✳` spinner glyph while "thinking"; tool calls in this
  exact two-line format (mono):
  `⏺ Bash(command here)` (coral ⏺)
  `  ⎿  output line` (dim)
  Title bar: traffic dots + "claude code — ~/myrepo".
- RIGHT (~50%): swaps content per beat (GitHub Actions run → PR list →
  ladder strip). GitHub panes use GitHub dark styling (like a real
  Actions page) but clearly stylized; Gusset panes use the app style
  (panel cards, ink borders, mono chips).

## The beats

### Beat 1 — Hand it to your agent (~20 s)
Claude Code pane active. User types: **"Set up gusset on this repo and
keep it maintained"**. Claude replies (one line): *"Reading the gusset
skill… installing autonomous mode."* Then, verbatim real output:

```
⏺ Bash(gusset init . --latchkey)
  ⎿  wrote gusset.toml and .github/workflows/gusset.yml
     Add ANTHROPIC_API_KEY (required) and PANDAPROBE_API_KEY /
     PANDAPROBE_PROJECT_NAME / HARNESS_REPAIR_MODEL (recommended)
     as repository secrets.
⏺ Bash(git add gusset.toml .github && git push)
  ⎿  main → main · 2 files changed
```

Caption: **"Hand it to your agent once — the skill teaches it the rest."**

### Beat 2 — The runner boots (~20 s)
Right pane: GitHub-Actions-run mock, workflow **"Gusset"**, job
**custodian**. Runner line highlighted with rust text:
`Runner: latchkey-small · online in 9.6s`. Steps check off in sequence
(green ✓ appearing one by one, the active one showing a spinner):
`Checkout ✓ · Install gusset ✓ · Install pandaprobe CLI ✓ · Route event ●→✓`.
Caption: **"Every push and PR fires the custodian — on Latchkey runners,
booted in seconds."**

### Beat 3 — The loop turns (~35 s)
Claude Code pane dims to "watching". Right pane cycles four moments
(cursor guides between them):

a. **PR comment lands** — mini GitHub comment card: small flowchart
   (rust seed box → green verified boxes) + text "Impact analysis · 8
   verified · 0 dropped at the gate". Caption: *"A PR opens → verified
   blast radius, commented autonomously."*
b. **Atlas PR arrives** — PR-list row: green "open" dot,
   `docs: refresh architecture atlas` · `gusset[bot]`. Caption:
   *"Structure shifted → the atlas PR arrives. propose level was
   human-granted in gusset.toml."*
c. **Cron tick** — ladder card `deadcode-zero · COMMENT` with a bar
   strip; one more green bar slides in, chip "run 16 ✓". Caption:
   *"Sunday cron → dead-code sweep. Every clean run climbs the ladder."*
d. **Self-heal** — an Actions step flips red ✗ → green ✓ with a small
   rust chip "self-healed". Caption: *"CI hiccup? Latchkey self-heals
   in-run; what it can't fix goes back to your agent."*

### Beat 4 — The loop, drawn (~12 s)
Both windows fade back; a cycle diagram draws itself in stage center
(panel nodes, ink arrows, rust highlights): **agent → push → runner →
custodian → PRs → review → merge ↺**. "review" node gets a subtle rust
ring (the human gate). Caption: **"You review PRs. Everything else runs,
measures, and repairs itself."**

## Ground-truth constraints (Daniel's rule: mock freely, invent nothing)

- Init output text: real (`gusset init --latchkey`), verbatim above.
- Action step names: real (from the shipped workflow file).
- "8 verified · 0 dropped": real PR #3 numbers.
- "run 16": follows the real 15-clean-run promotion in the ledger.
- 9.6s boot: Latchkey's published ~10s cold-start claim.
- Self-heal chip: their sidecar genuinely ran on our real CI failures —
  depict as a chip flip only, no invented logs.
- Claude coral only on Claude Code elements; Gusset rust never on them.

## Don'ts

- No fake OS chrome beyond the established window title bars.
- Green/red only for pass/fail semantics — never decoration.
- Captions one at a time, plain voice, each stating a WHY.
