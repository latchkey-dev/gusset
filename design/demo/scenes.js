/* ============================================================
   Gusset product demo — scene timeline.
   Every scene is { id, title, dur, steps: [[t_ms, action, ...args], ...] }.
   t is the offset from the start of the scene. demo.js compiles this
   into one flat, absolute-time event list (deterministic; seekable).

   GROUND TRUTH — CLI text is verbatim from design/demo/assets/:
     out-index.txt   → scene 2 index output
     pr-comment.md   → scene 3 verified impacts + scene 4 PR comment
     out-drift.txt   → scene 5 docs-drift output ("3 claims checked, 2 stale")
     out-ladder.jsonl→ scene 6 ledger lines
     skill-excerpt.txt → scene 7 SKILL.md panel
   Deviations are listed in design/demo/README.md ("asset gaps").
   ============================================================ */

/* ---- terminal line fragments (kept here so scenes stay readable) -------- */

// out-index.txt, verbatim (numbers wrapped in color spans only)
var T_INDEX_JSON =
  '{"db": ".gusset/graph.db", "files": <span class="g">102</span>, "symbols": <span class="g">798</span>, ' +
  '"edges": <span class="g">1521</span>, "packages": <span class="g">10</span>, ' +
  '"imports_external": 48, "unresolved_refs": <span class="y" id="tl-idx-unres">2744</span>}';

// scene 3 — the 8 verified impacts, qualnames verbatim from pr-comment.md
var T_IMPACT_OK = [
  '  <span class="g">✓</span> src.gusset.cli.atlas  <span class="dim">calls · d1</span>',
  '  <span class="g">✓</span> src.gusset.cli.docs_drift  <span class="dim">calls · d1</span>',
  '  <span class="g">✓</span> src.gusset.cli.impact  <span class="dim">calls · d1</span>',
  '  <span class="g">✓</span> src.gusset.serve.api.ServeState.__init__  <span class="dim">calls · d1</span>',
  '  <span class="g">✓</span> src.gusset.serve.api.ServeState.drift  <span class="dim">calls · d1</span>',
  '  <span class="g">✓</span> src.gusset.serve.server.make_handler.Handler.do_GET  <span class="dim">calls · d1</span>',
  '  <span class="g">✓</span> tests.test_serve.test_cli_impact_writes_runlog  <span class="dim">calls · d1</span>',
  '  <span class="g">✓</span> tests.test_serve.test_runlog_roundtrip_and_sessions  <span class="dim">calls · d1</span>'
];

// out-ladder.jsonl, verbatim (color spans only)
var T_LADDER_JSONL = [
  '<span class="dim">{"type": "run", "invariant": "deadcode-zero", "min_score": 1.0, "scores": {"deadcode_precision": 1.0}, "ts": "2026-08-18T20:49:01.045388+00:00"}</span>',
  '<span class="dim">{"type": "run", "invariant": "deadcode-zero", "min_score": 1.0, "scores": {"deadcode_precision": 1.0}, "ts": "2026-08-18T20:49:01.048650+00:00"}</span>',
  '<span id="tl-level">{"type": "level", "invariant": "deadcode-zero", "level": <span class="g">1</span>, "reason": "<span class="g">15 consecutive runs &gt;= 0.9</span>", "ts": "2026-08-18T20:49:01.049201+00:00"}</span>'
];

/* ---- the scenes --------------------------------------------------------- */

window.DEMO_SCENES = [

  /* 1 ── COLD OPEN ─────────────────────────────────────────────── ~20s */
  { id: 1, title: 'Cold open', dur: 20000, steps: [
    [0,     'titlecard', 7900],                       // logo draws itself, name + tagline
    [4200,  'caption', 'Gusset keeps a map of provable facts about your repo — and checks every AI claim against it.'],
    [8100,  'windowsIn'],
    [8900,  'showApp', 'graphEmpty'],
    [8900,  'termPrompt'],
    [9800,  'move', 955, 640, 1300],
    [18300, 'captionHide']
  ]},

  /* 2 ── THE MAP ───────────────────────────────────────────────── ~30s */
  { id: 2, title: 'The map', dur: 30000, steps: [
    [0,     'transition', '02', 'The map'],
    [1600,  'termCmd', 'gusset index .', 60],
    [3200,  'termOut', [T_INDEX_JSON], 400],
    [4400,  'showApp', 'graph'],
    [4900,  'caption', '798 symbols, 1,521 proven edges, 10 packages.'],
    [5400,  'move', 1340, 470, 1100],
    [8200,  'move', 1520, 350, 900],
    [11600, 'caption', 'Unresolved references are counted, never guessed — the map only holds facts.'],
    [12300, 'move', '#g-foot', 1000, 0, -8],
    [13500, 'highlight', '#g-foot', 3200],
    [18500, 'move', 1240, 520, 1000],
    [22000, 'move', '#tl-idx-unres', 900],
    [23000, 'highlight', '#tl-idx-unres', 2600],
    [27600, 'captionHide']
  ]},

  /* 3 ── IMPACT ────────────────────────────────────────────────── ~50s */
  { id: 3, title: 'Impact', dur: 50000, steps: [
    [0,     'transition', '03', 'Impact'],
    [1600,  'termCmd', 'gusset impact --symbol serve.events.RunLog.sessions', 45],
    [4400,  'termOut', [
      'seeds: src.gusset.serve.events.RunLog, src.gusset.serve.events.RunLog.sessions',
      '<span class="dim">building closure from graph @ 9981aa7 …</span>'
    ], 500],
    [5400,  'showApp', 'impact'],
    [5800,  'caption', 'The graph computes WHO is affected; the model only explains WHY.'],
    [6300,  'impSeed'],
    [6600,  'termOut', ['ring 1 · 8 confirmed call sites'], 0],
    [7200,  'impNode', 0], [7200,  'termOut', [T_IMPACT_OK[0]], 0],
    [7900,  'impNode', 1], [7900,  'termOut', [T_IMPACT_OK[1]], 0],
    [8600,  'impNode', 2], [8600,  'termOut', [T_IMPACT_OK[2]], 0],
    [9300,  'impNode', 3], [9300,  'termOut', [T_IMPACT_OK[3]], 0],
    [10000, 'impNode', 4], [10000, 'termOut', [T_IMPACT_OK[4]], 0],
    [10700, 'impNode', 5], [10700, 'termOut', [T_IMPACT_OK[5]], 0],
    [11400, 'impNode', 6], [11400, 'termOut', [T_IMPACT_OK[6]], 0],
    [12100, 'impNode', 7], [12100, 'termOut', [T_IMPACT_OK[7]], 0],
    [13800, 'caption', 'One claim didn’t check out — the gate dropped it. You never see unverified claims.'],
    [14500, 'impBad'],
    [14500, 'termOut', ['  <span class="r">✗ probe.tracing.flush_all</span>  <span class="r">edge not in graph</span>'], 0],
    [16300, 'impDrop'],
    [17400, 'termOut', ['gate: 9 claims checked → <span class="g">8 verified</span>, <span class="r">1 dropped</span>'], 0],
    [18600, 'impScores'],
    [18900, 'termOut', ['<span id="tl-cr">closure_recall <span class="g">1.00</span> · summary_grounding <span class="g">1.00</span> · gate_drop_rate 0.11</span>'], 0],
    [20200, 'caption', 'closure_recall 1.0 — nothing reachable was missed.'],
    [20800, 'move', '#sc-cr-row', 900],
    [21900, 'highlight', '#sc-cr-row', 2800],
    [25200, 'termOut', ['<span class="dim">wrote report → .gusset/impact/impact-6f4a10a373ef.md</span>'], 0],
    [26400, 'move', '#imp-ledger', 1000],
    [27600, 'highlight', '#imp-ledger', 2800],
    [31500, 'caption', 'Every row carries its edge — drops are logged, never hidden.'],
    [33500, 'termPrompt'],
    [37000, 'move', 700, 560, 1100],
    [42000, 'captionHide']
  ]},

  /* 4 ── THE PR ────────────────────────────────────────────────── ~45s */
  { id: 4, title: 'The pull request', dur: 45000, steps: [
    [0,     'transition', '04', 'The pull request'],
    [1600,  'caption', 'The same thing happens autonomously on every pull request.'],
    [2200,  'termCmd', 'git push origin runlog-sessions', 42],
    [4100,  'termOut', [
      'Enumerating objects: 12, done.',
      'Counting objects: 100% (12/12), done.',
      'Writing objects: 100% (7/7), 1.94 KiB | 1.94 MiB/s, done.',
      'To github.com:latchkey-dev/gusset.git',
      '   9981aa7..4c11f2e  runlog-sessions -> runlog-sessions'
    ], 320],
    [6600,  'termOut', ['<span class="dim">gusset custodian · impact-on-pr → running on PR #3 …</span>'], 0],
    [9000,  'termOut', ['<span class="g">✓</span> gusset[bot] commented on <span class="rust">PR #3</span>'], 0],
    [9800,  'showApp', 'pr'],
    [10600, 'caption', 'A verified blast-radius comment, with the diagram, on the PR itself.'],
    [11400, 'move', '#pr-diagram', 1100],
    /* drag-scroll: press, pull the page up while the content follows, release */
    [15300, 'move', 1350, 640, 900],
    [16200, 'clickDown'],
    [16350, 'pulseGone'],
    [16400, 'move', 1350, 330, 1500],
    [16400, 'scrollApp', -300, 1500],
    [18000, 'clickUp'],
    [18500, 'caption', 'Reviewers see what a change touches — with proof, not vibes.'],
    [19200, 'move', '#pr-seeds', 900],
    [23000, 'scrollApp', -540, 1800],
    [25400, 'move', '#pr-footer', 1000],
    [26600, 'highlight', '#pr-footer', 3200],
    [32000, 'move', '#pr-bullets', 900, 0, -20],
    [34500, 'termPrompt'],
    [41500, 'captionHide']
  ]},

  /* 5 ── DRIFT ─────────────────────────────────────────────────── ~40s */
  { id: 5, title: 'Docs drift', dur: 40000, steps: [
    [0,     'transition', '05', 'Docs drift'],
    [1600,  'termCmd', 'gusset docs-drift docs/', 55],
    [3500,  'termOut', [
      'wrote /tmp/dd.md — 3 claims checked, <span class="r">3 stale</span>',
      '<span class="dim">exit=2 (drift found — usable as a CI check)</span>'
    ], 450],
    [4800,  'showApp', 'drift'],
    [5600,  'caption', 'Docs are checked against the graph — stale references surface with their line numbers.'],
    [6400,  'move', '#stale-0 .loc', 1100],
    [7700,  'highlight', '#stale-0 .loc', 2400],
    [11600, 'caption', 'One click teaches it: stdlib names aren’t drift. The CLI respects the same allowlist.'],
    [12600, 'move', '#drift-allow-0', 900],
    [13800, 'click'],
    [14100, 'driftAllow'],
    [17200, 'termCmd', 'gusset docs-drift docs/', 55],
    [19200, 'termOut', [
      'wrote /tmp/dd.md — 3 claims checked, <span id="tl-stale2" class="g">2 stale</span>',
      '<span class="dim">trace: https://app.pandaprobe.com/sessions?search=docsdrift-6c995b75337b</span>',
      '<span class="dim">… telemetry retry lines trimmed …</span>',
      '<span class="dim">exit=2 (drift found — usable as a CI check)</span>'
    ], 420],
    [21600, 'highlight', '#tl-stale2', 2600],
    [25000, 'move', '#drift-pill', 1100],
    [26300, 'highlight', '#drift-pill', 2600],
    [30500, 'termPrompt'],
    [31000, 'move', 1100, 620, 1100],
    [36500, 'captionHide']
  ]},

  /* 6 ── LADDER ────────────────────────────────────────────────── ~40s */
  { id: 6, title: 'The ladder', dur: 40000, steps: [
    [0,     'transition', '06', 'The ladder'],
    [1600,  'showApp', 'ladder'],
    [2400,  'caption', 'Autonomy is earned: 15 clean runs to climb, 3 bad in 5 to fall.'],
    [3000,  'move', '#dz-card', 1100, 0, 10],
    [4200,  'ladderRun', 15, 300],
    [9600,  'ladPromote'],
    [12000, 'termCmd', 'tail -n 3 .gusset/ladder.jsonl', 45],
    [14000, 'termOut', T_LADDER_JSONL, 650],
    [16800, 'highlight', '#tl-level', 2800],
    [19200, 'caption', 'The top rung can only ever be granted by a human, in gusset.toml.'],
    [20200, 'move', '#lad-act-rule', 1100],
    [21500, 'highlight', '#lad-act-rule', 3000],
    [26500, 'move', '#dz-chip', 1000],
    [28000, 'termPrompt'],
    [36500, 'captionHide']
  ]},

  /* 7 ── AGENTS ────────────────────────────────────────────────── ~35s */
  { id: 7, title: 'Agents drive it', dur: 35000, steps: [
    [0,     'transition', '07', 'Agents drive it'],
    [1600,  'termTitle', 'terminal — claude code'],
    [1600,  'termClear', 'claude'],
    [2000,  'showApp', 'skill'],
    [2600,  'caption', 'Your AI tool drives Gusset for you — the skill teaches it when to run what, and which scores to trust.'],
    [3200,  'termCmd', 'what will breaking RunLog.sessions affect?', 38, '> '],
    [5900,  'termOut', ['', '<span class="cl-dot">⏺</span> I’ll check the verified blast radius with Gusset.'], 200],
    [7400,  'termOut', ['', '<span class="cl-dot">⏺</span> <span class="rust">Bash(gusset impact --symbol serve.events.RunLog.sessions)</span>'], 200],
    [8800,  'termOut', ['  <span class="dim">⎿</span>  <span class="g">8 verified impacts</span> · <span class="r">1 dropped at the gate</span> · closure_recall <span class="g">1.00</span>'], 0],
    [10600, 'termOut', [
      '',
      '<span class="cl-dot">⏺</span> Breaking <span class="rust">RunLog.sessions</span> reaches the read path and two tests:',
      '<span id="tl-checklist">    api.ServeState.drift — consumes RunLog.sessions</span>',
      '    make_handler.Handler.do_GET — serves sessions data to clients',
      '    tests.test_serve.test_runlog_roundtrip_and_sessions',
      '    tests.test_serve.test_cli_impact_writes_runlog',
      '  Every item has a proven edge — that list is my edit checklist.'
    ], 420],
    [14200, 'move', '#skill-impact-row', 1200],
    [15600, 'highlight', '#skill-impact-row', 2800],
    [19200, 'caption', 'The verified impact list becomes the agent’s edit checklist.'],
    [20200, 'move', '#tl-checklist', 1100],
    [21500, 'highlight', '#tl-checklist', 2800],
    [26000, 'move', 900, 500, 1100],
    [31500, 'captionHide']
  ]},

  /* 8 ── CLOSE ─────────────────────────────────────────────────── ~20s */
  { id: 8, title: 'Close', dur: 20000, steps: [
    [0,    'captionHide'],
    [200,  'sceneTitle', '08 — Close'],
    [300,  'shrinkWins'],
    [1400, 'closeCard'],
    [2800, 'caption', 'Gusset — autonomous self-healing repo upkeep.'],
    [4000, 'move', 960, 780, 1400]
  ]}
];
