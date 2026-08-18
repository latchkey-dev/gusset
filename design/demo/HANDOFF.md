# Gusset demo — Claude Design handoff package

Everything needed to build (or restyle) the product-demo animation in
Claude Design. The in-repo animated build lives at `design/demo/demo.html`
(engine + scenes); this package is for iterating on it in Design instead.

## Design system (authoritative)

- Tokens: `design/Main.dc.html` (the token table — Paper + Chalkboard
  values). Demo plays in **Paper**.
- Fonts: Archivo 400/600/800 (UI, captions) + Spline Sans Mono 400/500
  (terminal, qualnames, scores). Google Fonts.
- Logo: three concentric circles — rust `#B4551E` filled dot, ink
  `#22211D` ring (stroke 7/104), dashed `#8A8577` outer ring (stroke 5,
  dash 9 10). Never recolor per theme role.
- Window chrome: 1.5px ink border, hard offset shadow `3px 3px 0 #D9D3C4`,
  radius 4px. Terminal dark: bg `#14130F`, text `#EDE8DB`.
- Ground: `#F4F1EA` with drafting dots (`radial-gradient(#D9D3C4 1px,
  transparent 1px)`, 24px grid).
- Semantics (never repurpose): verified/pass green `#2E7D4F`, dropped/
  stale red `#C23934`, selection/accent rust `#B4551E`.

## Approved screen references (mock these, don't invent)

`design/ViewGraph.dc.html`, `ViewImpact.dc.html`, `ViewWorkflow.dc.html`,
`ViewDrift.dc.html`, `ViewLadder.dc.html`, `ViewSetup.dc.html` — the six
approved boards. The serve app they describe is real and running; live
screenshots in `assets/serve-impact.png` (+ more on request).

## Ground truth per scene (in `assets/`) — all REAL outputs

| Scene | Asset | Source |
|---|---|---|
| The map | `out-index.txt` | `gusset index .` on this repo (798 symbols, 1,521 edges, 10 packages) |
| Impact | `pr-comment.md` verified list | the custodian's actual PR #3 comment |
| PR | `pr-comment.md` + `gh-video` recording | real GitHub page, real Mermaid rendering |
| Drift | `out-drift.txt` | real run: 2 stale after a real allowlist entry |
| Deadcode | `out-deadcode.txt` | real query output |
| Ladder | `out-ladder.jsonl` | the actual ledger — deadcode-zero promoted after 15 real runs |
| Agents | `skill-excerpt.txt` | shipped `skills/gusset/SKILL.md` |

Mocking rule (Daniel's): simplify freely, but every capability shown must
exist and every number must trace to one of these assets.

## Scene script (8 scenes, ~4–6 min)

1. Cold open — logo draw-on, thesis caption: "Gusset keeps a map of
   provable facts about your repo — and checks every AI claim against it."
2. The map — terminal `gusset index .` (real output) ⇄ graph view fills.
3. Impact — terminal run ⇄ impact view animates: rings pop green, one
   claim flashes red and is dropped at the gate; score bars fill.
4. The PR — push ⇄ the GitHub comment (splice the REAL recording:
   `gh-video/`, 26s, logged-in PR #3 with rendered Mermaid).
5. Drift — terminal 3-stale ⇄ drift view; cursor clicks allowlist; card
   exits; terminal re-run shows 2. (Real allowlist file round-trip.)
6. Ladder — bar strip fills run by run; promotion chip flips (real ledger
   event: "15 consecutive runs >= 0.9"); "ACT is human-granted only."
7. Agents — Claude-Code-style pane invokes gusset via the skill; verified
   list becomes the agent's edit checklist.
8. Close — logo + tagline "Autonomous self-healing repo upkeep."

Caption voice: plain, one sentence at a time, always saying WHY
("The graph computes WHO is affected; the model only explains WHY").
Cursor is the narrative guide: move → click-pulse → dwell.
