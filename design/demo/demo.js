/* ============================================================
   Gusset product demo — timeline engine.
   - Compiles window.DEMO_SCENES into one flat, absolute-time event list.
   - requestAnimationFrame scheduler; deterministic (fixed timings only).
   - window.demoPlay()   → start / resume playback
   - window.demoSeek(ms) → rebuild stage and instant-apply all events ≤ ms
   - window.demoDuration → total length in ms
   ============================================================ */

(function () {
  'use strict';

  /* ---------- small helpers ---------------------------------------------- */

  var $ = function (sel) { return document.querySelector(sel); };

  function logoSVG(size, cls) {
    return '<svg class="' + (cls || '') + '" width="' + size + '" height="' + size + '" viewBox="0 0 104 104" fill="none">' +
      '<circle class="ld-dot" cx="52" cy="52" r="10" fill="#b4551e"/>' +
      '<circle class="ld-ring1" cx="52" cy="52" r="26" stroke="#22211d" stroke-width="7" pathLength="1"/>' +
      '<circle class="ld-ring2" cx="52" cy="52" r="42" stroke="#8a8577" stroke-width="5" stroke-dasharray="9 10"/>' +
      '</svg>';
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = a + 0x6D2B79F5 | 0;
      var t = Math.imul(a ^ a >>> 15, 1 | a);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  /* ---------- stage skeleton --------------------------------------------- */

  var CURSOR_SVG =
    '<svg width="30" height="32" viewBox="0 0 30 32" fill="none">' +
    '<path d="M3 1.5 L3 25 L9.2 19.6 L13 29 L17.6 27 L13.9 17.9 L22.5 17.3 Z" ' +
    'fill="#22211d" stroke="#fdfcf8" stroke-width="1.8" stroke-linejoin="round"/></svg>';

  var STAGE_HTML =
    '<div id="topbar">' +
      logoSVG(28) +
      '<span class="wordmark">GUSSET</span>' +
      '<span class="tb-sub">product demo</span>' +
      '<span id="scene-title"></span>' +
    '</div>' +
    '<div id="win-term" class="win offstage">' +
      '<div class="win-title"><span class="dot d-r"></span><span class="dot d-y"></span><span class="dot d-g"></span>' +
      '<span class="win-name" id="term-name">terminal — gusset</span></div>' +
      '<div id="term" class="term-body"></div>' +
    '</div>' +
    '<div id="win-app" class="win offstage">' +
      '<div class="win-title"><span class="dot d-r"></span><span class="dot d-y"></span><span class="dot d-g"></span>' +
      '<span class="win-name" id="app-name">gusset serve — localhost:8321</span></div>' +
      '<div id="app" class="app-body"></div>' +
    '</div>' +
    '<div id="caption" class="hidden"></div>' +
    '<div id="cursor">' + CURSOR_SVG + '</div>' +
    '<div id="overlay"></div>';

  /* ---------- shared app-mock fragments ----------------------------------- */

  var TABS = ['GRAPH', 'IMPACT', 'WORKFLOW', 'DRIFT', 'LADDER', 'SETUP'];

  function appHeader(active, meta) {
    var tabs = TABS.map(function (t) {
      return '<span class="av-tab' + (t === active ? ' on' : '') + '">' + t + '</span>';
    }).join('');
    return '<div class="av-hdr">' + logoSVG(20) +
      '<span class="av-wordmark">GUSSET</span>' +
      '<span class="av-meta">' + meta + '</span>' +
      '<div class="av-tabs">' + tabs + '</div></div>';
  }

  function graphSide(indexed) {
    var foot = indexed
      ? '798 symbols · 1,521 edges<br>10 packages · 102 files<br><span id="g-unres">2,744 unresolved (counted,<br>never guessed)</span>'
      : 'no graph yet —<br>run <span style="color:#b4551e">gusset index .</span>';
    function frow(on, label) {
      return '<div class="filter-row"><span class="cbox' + (on ? ' on' : '') + '"></span> ' + label + '</div>';
    }
    return '<div class="g-side">' +
      '<div class="searchbox"><svg width="12" height="12" viewBox="0 0 20 20" fill="none">' +
      '<circle cx="8" cy="8" r="5" stroke="#6b675c" stroke-width="1.6"/><path d="M12 12 L17 17" stroke="#6b675c" stroke-width="1.6"/></svg>' +
      'search symbols…</div>' +
      '<div style="display:flex;flex-direction:column;gap:8px"><div class="k">SHOW</div>' +
      frow(true, 'functions') + frow(true, 'classes &amp; methods') + frow(true, 'modules') + frow(false, 'packages') +
      '</div>' +
      '<div style="display:flex;flex-direction:column;gap:8px"><div class="k">LEGEND</div>' +
      '<div class="legend-row"><span class="lg-sym"></span> symbol</div>' +
      '<div class="legend-row"><span class="lg-sel"></span> selected</div>' +
      '<div class="legend-row"><span class="lg-pkg"></span> package (external)</div>' +
      '<div class="legend-row"><span class="lg-edge"></span> edge of selection</div>' +
      '</div>' +
      '<div class="side-foot" id="g-foot">' + foot + '</div>' +
      '</div>';
  }

  /* deterministic node field for the GRAPH view (positions are invented;
     the counts shown in the sidebar footer are real, from out-index.txt).
     Airy per the ViewGraph board: local clusters, few cross-cluster edges. */
  function graphFieldSVG() {
    var rnd = mulberry32(11);
    var clusters = [
      { cx: 150, cy: 180, label: 'graph.store.GraphStore', hr: 10 },
      { cx: 410, cy: 130, label: 'workflows.impact', hr: 11 },
      { cx: 622, cy: 268, label: 'serve.events.RunLog', hr: 13, main: true },
      { cx: 300, cy: 420, label: 'cli.impact', hr: 11 },
      { cx: 140, cy: 510, hr: 8 },
      { cx: 565, cy: 495, label: 'supervisor.ladder.Ladder', hr: 10 }
    ];
    var pkgs = [
      { x: 722, y: 108, label: 'tree_sitter (pkg)' },
      { x: 712, y: 560, label: 'langgraph (pkg)' }
    ];
    var edgesSVG = '', circSVG = '', textSVG = '', k = 0, delay;
    var hubs = [];
    clusters.forEach(function (c, ci) {
      var hub = { x: c.cx, y: c.cy };
      hubs.push(hub);
      var fillers = [];
      var n = 4 + Math.floor(rnd() * 2);
      for (var i = 0; i < n; i++) {
        var ang = rnd() * Math.PI * 2;
        var dist = 52 + rnd() * 62;
        fillers.push({
          x: Math.max(25, Math.min(760, Math.round(c.cx + Math.cos(ang) * dist))),
          y: Math.max(45, Math.min(585, Math.round(c.cy + Math.sin(ang) * dist * 0.85))),
          r: 5 + Math.round(rnd() * 5)
        });
      }
      fillers.forEach(function (f, fi) {
        delay = 480 + (ci * 5 + fi) * 42;
        var from = (fi > 0 && rnd() > 0.55) ? fillers[fi - 1] : hub;
        edgesSVG += '<path class="gedge" style="animation-delay:' + delay + 'ms" d="M' + from.x + ' ' + from.y +
          ' L' + f.x + ' ' + f.y + '" stroke="#c9c2af" stroke-width="1.15"/>';
        circSVG += '<circle class="gnode" style="animation-delay:' + (140 + k * 48) + 'ms" cx="' + f.x + '" cy="' + f.y +
          '" r="' + f.r + '" fill="#fdfcf8" stroke="#8a8577" stroke-width="1.4"/>';
        k++;
      });
      circSVG += '<circle class="gnode" style="animation-delay:' + (140 + k * 48) + 'ms" cx="' + c.cx + '" cy="' + c.cy +
        '" r="' + c.hr + '" fill="' + (c.main ? '#f6e3d3' : '#fdfcf8') + '" stroke="' +
        (c.main ? '#b4551e' : (c.label ? '#22211d' : '#8a8577')) + '" stroke-width="' + (c.label ? 1.8 : 1.4) + '"/>';
      k++;
      if (c.label) {
        textSVG += '<text class="gnode" style="animation-delay:' + (900 + ci * 130) + 'ms" x="' + c.cx + '" y="' + (c.cy + c.hr + 15) +
          '" text-anchor="middle" font-family="Spline Sans Mono" font-size="9.5" fill="' +
          (c.main ? '#b4551e' : '#6b675c') + '">' + c.label + '</text>';
      }
    });
    /* a few curated cross-cluster edges between hubs */
    [[0, 1], [1, 2], [3, 2], [3, 4], [5, 2], [3, 1]].forEach(function (p, i) {
      edgesSVG = '<path class="gedge" style="animation-delay:' + (700 + i * 90) + 'ms" d="M' + hubs[p[0]].x + ' ' + hubs[p[0]].y +
        ' L' + hubs[p[1]].x + ' ' + hubs[p[1]].y + '" stroke="#c9c2af" stroke-width="1.3"/>' + edgesSVG;
    });
    pkgs.forEach(function (p, i) {
      circSVG += '<circle class="gnode" style="animation-delay:' + (1700 + i * 160) + 'ms" cx="' + p.x + '" cy="' + p.y +
        '" r="8" fill="none" stroke="#8a8577" stroke-width="1.5" stroke-dasharray="3 3"/>';
      textSVG += '<text class="gnode" style="animation-delay:' + (1800 + i * 160) + 'ms" x="' + p.x + '" y="' + (p.y - 14) +
        '" text-anchor="middle" font-family="Spline Sans Mono" font-size="9" fill="#8a8577">' + p.label + '</text>';
    });
    return '<svg width="100%" height="100%" viewBox="0 0 785 619" fill="none" preserveAspectRatio="xMidYMid meet">' +
      edgesSVG + circSVG + textSVG + '</svg>';
  }

  /* ---------- views ------------------------------------------------------- */

  var VIEW_TITLES = {
    graphEmpty: 'gusset serve — localhost:8321',
    graph: 'gusset serve — localhost:8321',
    impact: 'gusset serve — localhost:8321',
    pr: 'github.com — latchkey-dev/gusset — PR #3',
    drift: 'gusset serve — localhost:8321',
    ladder: 'gusset serve — localhost:8321',
    skill: 'skills/gusset/SKILL.md'
  };

  var VIEWS = {};

  VIEWS.graphEmpty = function () {
    return '<div class="appview">' + appHeader('GRAPH', 'latchkey-dev/gusset') +
      '<div class="av-body">' + graphSide(false) +
      '<div class="g-stage dotbg"><div class="empty-wrap" style="height:100%">' +
      '<div class="empty"><div class="title">No graph yet</div>' +
      '<div class="sentence">Run <span class="mono">gusset index .</span> to build the map — every symbol, every call/import/inheritance edge, every package. Facts only.</div>' +
      '</div></div></div></div></div>';
  };

  VIEWS.graph = function () {
    return '<div class="appview">' + appHeader('GRAPH', 'latchkey-dev/gusset @ 9981aa7') +
      '<div class="av-body">' + graphSide(true) +
      '<div class="g-stage dotbg">' + graphFieldSVG() +
      '<div class="overlay-chips"><span class="chip">fit</span><span class="chip dim">100%</span></div>' +
      '</div></div></div>';
  };

  /* impact — geometry for the blast-radius run animation.
     Labels are anchored per node so they never collide around the ring. */
  var IMP_C = { x: 330, y: 306 };
  var IMP_R = 118;
  var IMP_NODES = [
    { a: -90, label: 'gusset.cli.atlas', anchor: 'middle', dx: 0, dy: -18 },
    { a: -45, label: 'gusset.cli.docs_drift', anchor: 'start', dx: 15, dy: -8 },
    { a: 0, label: 'gusset.cli.impact', anchor: 'start', dx: 17, dy: 4 },
    { a: 45, label: 'api.ServeState.__init__', anchor: 'start', dx: 15, dy: 15 },
    { a: 90, label: 'api.ServeState.drift', anchor: 'middle', dx: 0, dy: 26 },
    { a: 135, label: 'make_handler.Handler.do_GET', anchor: 'end', dx: -15, dy: 15 },
    { a: 180, label: 'tests…cli_impact_writes_runlog', anchor: 'end', dx: -17, dy: 4 },
    { a: 225, label: 'tests…runlog_roundtrip_and_sessions', anchor: 'end', dx: -14, dy: -9 }
  ];
  function impPos(n) {
    var rad = n.a * Math.PI / 180;
    return { x: IMP_C.x + IMP_R * Math.cos(rad), y: IMP_C.y + IMP_R * Math.sin(rad) };
  }

  VIEWS.impact = function () {
    function scoreRow(id, name) {
      return '<div class="score-row" id="' + id + '-row"><span class="name">' + name + '</span>' +
        '<div class="bar"><div id="' + id + '"></div></div><span class="val" id="' + id + 'v">—</span></div>';
    }
    return '<div class="appview">' + appHeader('IMPACT', 'impact · session impact-6f4a10a373ef') +
      '<div class="av-body">' +
      '<div class="i-stage dotbg">' +
      '<svg width="100%" height="100%" viewBox="0 0 657 619" fill="none" preserveAspectRatio="xMidYMid meet">' +
      '<circle cx="' + IMP_C.x + '" cy="' + IMP_C.y + '" r="' + IMP_R + '" stroke="#22211d" stroke-width="1.6"/>' +
      '<circle cx="' + IMP_C.x + '" cy="' + IMP_C.y + '" r="225" stroke="#8a8577" stroke-width="1.3" stroke-dasharray="6 7"/>' +
      '<text x="180" y="180" font-family="Spline Sans Mono" font-size="10" fill="#8a8577">DEPTH 1</text>' +
      '<text x="82" y="80" font-family="Spline Sans Mono" font-size="10" fill="#8a8577">DEPTH 2</text>' +
      '<g id="imp-nodes"></g>' +
      '</svg></div>' +
      '<div class="i-side">' +
      '<div style="display:flex;flex-direction:column;gap:4px"><div class="k">SEEDS</div>' +
      '<span class="sel-qual">serve.events.RunLog</span>' +
      '<span class="sel-qual">serve.events.RunLog.sessions</span>' +
      '<div class="sel-sub">from --symbol · graph @ 9981aa7</div></div>' +
      '<div class="stat3">' +
      '<div class="verified"><div class="n" id="st-ver">0</div><div class="l">VERIFIED</div></div>' +
      '<div class="dropped"><div class="n" id="st-drop">0</div><div class="l">DROPPED</div></div>' +
      '<div class="rings"><div class="n">1</div><div class="l">RINGS</div></div></div>' +
      '<div style="display:flex;flex-direction:column;gap:6px"><div class="k">ORACLE SCORES</div>' +
      scoreRow('sc-cr', 'closure_recall') + scoreRow('sc-sg', 'summary_grounding') + scoreRow('sc-gd', 'gate_drop_rate') +
      '</div>' +
      '<div style="flex:1;display:flex;flex-direction:column;gap:6px;min-height:0"><div class="k">CLAIM LEDGER</div>' +
      '<div class="ledger-box" id="imp-ledger"></div>' +
      '<div class="footnote">Every row carries its edge; drops are logged, never hidden.</div></div>' +
      '<div style="display:flex;gap:8px"><div class="btn pass">Approve report</div><div class="btn">View markdown</div></div>' +
      '</div></div></div>';
  };

  /* PR comment — content verbatim from design/demo/assets/pr-comment.md */
  function prDiagramSVG() {
    var passLabels = [
      'gusset.cli.atlas', 'gusset.cli.docs_drift', 'gusset.cli.impact', 'api.ServeState.__init__',
      'api.ServeState.drift', 'make_handler.Handler.do_GET',
      'tests.test_serve.test_cli_impact_writes_runlog', 'tests.test_serve.test_runlog_roundtrip_and_sessions'
    ];
    // edge map from the mermaid block: n0 → atlas, docs_drift, impact, __init__, test_cli…; n1 → drift, do_GET, test_runlog…
    var fromN0 = [0, 1, 2, 3, 6], fromN1 = [4, 5, 7];
    var s = '';
    var rowY = function (i) { return 12 + i * 42; };
    fromN0.forEach(function (i) {
      s += '<path d="M280 82 C 360 82, 350 ' + (rowY(i) + 15) + ', 428 ' + (rowY(i) + 15) + '" stroke="#8a8577" stroke-width="1.4" fill="none"/>';
    });
    fromN1.forEach(function (i) {
      s += '<path d="M280 232 C 360 232, 350 ' + (rowY(i) + 15) + ', 428 ' + (rowY(i) + 15) + '" stroke="#8a8577" stroke-width="1.4" fill="none"/>';
    });
    s += '<rect x="20" y="60" width="260" height="44" rx="8" fill="#b4551e" stroke="#22211d" stroke-width="1.5"/>' +
      '<text x="150" y="87" text-anchor="middle" font-family="Spline Sans Mono" font-size="11.5" fill="#ffffff">◉ serve.events.RunLog</text>' +
      '<rect x="20" y="210" width="260" height="44" rx="8" fill="#b4551e" stroke="#22211d" stroke-width="1.5"/>' +
      '<text x="150" y="237" text-anchor="middle" font-family="Spline Sans Mono" font-size="11.5" fill="#ffffff">◉ events.RunLog.sessions</text>';
    passLabels.forEach(function (lab, i) {
      s += '<rect x="428" y="' + rowY(i) + '" width="432" height="30" rx="6" fill="#eef5ef" stroke="#2e7d4f" stroke-width="1.4"/>' +
        '<text x="444" y="' + (rowY(i) + 19) + '" font-family="Spline Sans Mono" font-size="10.5" fill="#22211d">' + lab + '</text>';
    });
    return '<svg width="100%" viewBox="0 0 880 350" fill="none">' + s + '</svg>';
  }

  VIEWS.pr = function () {
    return '<div class="appview"><div class="pr-body"><div id="pr-scroll" class="pr-scroll">' +
      '<div class="pr-comment">' +
      '<div class="pr-hdr">' + logoSVG(26) + '<b>gusset[bot]</b> commented just now' +
      '<span class="pr-bot-badge">bot</span><span style="margin-left:auto">PR #3 · latchkey-dev/gusset</span></div>' +
      '<div class="pr-md">' +
      '<div class="pr-diagram" id="pr-diagram">' + prDiagramSVG() + '</div>' +
      '<h1>Impact analysis</h1>' +
      '<p id="pr-seeds"><b>Seeds:</b> <code>src.gusset.serve.events.RunLog</code>, <code>src.gusset.serve.events.RunLog.sessions</code></p>' +
      '<p>Changes to <code>RunLog</code> and <code>RunLog.sessions</code> propagate to eight confirmed call sites. ' +
      'On the constructor/write path, <code>src.gusset.cli.impact</code>, <code>src.gusset.cli.atlas</code>, and ' +
      '<code>src.gusset.cli.docs_drift</code> all construct and invoke <code>RunLog</code> to record run results, and ' +
      '<code>src.gusset.serve.api.ServeState.__init__</code> initializes server state with a <code>RunLog</code> instance, ' +
      'so signature, default, or persistence changes can break these commands and server startup. ' +
      '<span class="pr-dim">… (full summary in the report)</span></p>' +
      '<h2>Verified impacts</h2>' +
      '<ul id="pr-bullets">' +
      '<li><code>src.gusset.cli.atlas</code> — depth 1, calls edge to <code>src.gusset.serve.events.RunLog</code>: ' +
      'This command calls RunLog to emit run records, so changes to RunLog\'s API or persistence semantics could cause ' +
      'call-site errors or missing/malformed atlas run entries.</li>' +
      '<li><code>src.gusset.cli.docs_drift</code> — depth 1, calls edge to <code>src.gusset.serve.events.RunLog</code>: ' +
      'It calls RunLog when reporting docs-drift results, so altered RunLog behavior or arguments could break the command ' +
      'or change the drift output it records.</li>' +
      '<li><code>src.gusset.cli.impact</code> — depth 1, calls edge to <code>src.gusset.serve.events.RunLog</code>: ' +
      'It directly constructs/invokes RunLog to record impact-analysis runs, so any change to RunLog\'s constructor ' +
      'signature, defaults, or write behavior can break or alter this CLI command\'s logging path.</li>' +
      '<li class="pr-dim">… 5 more verified impacts in the full comment</li>' +
      '</ul>' +
      '<p class="pr-foot" id="pr-footer"><em>8 claims verified against the code graph; 0 dropped at the gate.</em></p>' +
      '</div></div></div></div></div>';
  };

  /* drift — data reconciled to out-drift.txt (3 claims checked);
     reference names/lines/explanations from the approved ViewDrift board */
  VIEWS.drift = function () {
    var svg =
      '<svg width="100%" height="100%" viewBox="0 0 625 619" fill="none" preserveAspectRatio="xMidYMid meet">' +
      // tethers
      '<g class="teth" id="teth-0">' +
      '<path d="M232 178 C 320 175, 350 180, 424 185" stroke="#c23934" stroke-width="1.8" stroke-dasharray="6 5" fill="none"/>' +
      '<circle cx="432" cy="185" r="9" fill="none" stroke="#c23934" stroke-width="1.8" stroke-dasharray="3 3"/>' +
      '<path d="M427 180 l10 10 M437 180 l-10 10" stroke="#c23934" stroke-width="1.6"/>' +
      '<text x="432" y="212" text-anchor="middle" font-family="Spline Sans Mono" font-size="9.5" fill="#c23934">asyncio.to_thread</text>' +
      '<text x="432" y="226" text-anchor="middle" font-family="Spline Sans Mono" font-size="8.5" fill="#8a8577">external, not in graph</text>' +
      '<text class="allow-tag" x="432" y="160" text-anchor="middle" font-family="Spline Sans Mono" font-size="9" fill="#2e7d4f">allowlisted ✓</text>' +
      '</g>' +
      '<g class="teth" id="teth-1">' +
      '<path d="M232 190 C 330 210, 370 270, 444 300" stroke="#c23934" stroke-width="1.8" stroke-dasharray="6 5" fill="none"/>' +
      '<circle cx="452" cy="302" r="9" fill="none" stroke="#c23934" stroke-width="1.8" stroke-dasharray="3 3"/>' +
      '<path d="M447 297 l10 10 M457 297 l-10 10" stroke="#c23934" stroke-width="1.6"/>' +
      '<text x="448" y="329" text-anchor="middle" font-family="Spline Sans Mono" font-size="9" fill="#c23934">tree_sitter_language_pack.get_parser</text>' +
      '</g>' +
      '<g class="teth" id="teth-2">' +
      '<path d="M232 418 C 320 430, 360 455, 424 468" stroke="#c23934" stroke-width="1.8" stroke-dasharray="6 5" fill="none"/>' +
      '<circle cx="432" cy="470" r="9" fill="none" stroke="#c23934" stroke-width="1.8" stroke-dasharray="3 3"/>' +
      '<path d="M427 465 l10 10 M437 465 l-10 10" stroke="#c23934" stroke-width="1.6"/>' +
      '<text x="432" y="497" text-anchor="middle" font-family="Spline Sans Mono" font-size="9.5" fill="#c23934">pull_request_target</text>' +
      '</g>' +
      // doc cards
      '<g><rect x="40" y="150" width="192" height="56" rx="3" fill="#fbeae9" stroke="#c23934" stroke-width="2"/>' +
      '<text x="136" y="173" text-anchor="middle" font-family="Spline Sans Mono" font-size="10" fill="#22211d">howto/write-a-workflow.md</text>' +
      '<text id="docA-sub" x="136" y="191" text-anchor="middle" font-family="Spline Sans Mono" font-size="9" fill="#c23934">2 refs · 2 stale</text></g>' +
      '<g><rect x="40" y="390" width="192" height="56" rx="3" fill="#fbeae9" stroke="#c23934" stroke-width="2"/>' +
      '<text x="136" y="413" text-anchor="middle" font-family="Spline Sans Mono" font-size="10" fill="#22211d">reference/cli.md</text>' +
      '<text id="docB-sub" x="136" y="431" text-anchor="middle" font-family="Spline Sans Mono" font-size="9" fill="#c23934">1 ref · 1 stale</text></g>' +
      '</svg>';

    function staleCard(id, sym, loc, why, chips) {
      return '<div class="stale-card" id="' + id + '">' +
        '<div class="head"><span class="sym">' + sym + '</span><span class="loc">' + loc + '</span></div>' +
        '<div class="why">' + why + '</div>' + (chips || '') + '</div>';
    }
    return '<div class="appview">' + appHeader('DRIFT', 'drift · docs/ · 3 references checked') +
      '<div class="av-body">' +
      '<div class="d-stage dotbg">' + svg +
      '<div class="drift-pill" id="drift-pill"><span class="dim">docs/</span><span>3 checked</span>' +
      '<span class="r" id="pill-stale">3 stale</span><span class="dim">docs → symbols</span></div>' +
      '</div>' +
      '<div class="d-side">' +
      '<div class="d-side-head"><div class="k">STALE REFERENCES</div></div>' +
      '<div class="d-cards" id="d-cards">' +
      staleCard('stale-0', 'asyncio.to_thread', 'howto/write-a-workflow.md:50',
        'Resolves to no symbol in the graph. Likely an <b>external stdlib reference</b> — candidate for the allowlist, not a docs fix.',
        '<div class="chips"><span class="chipbtn" id="drift-allow-0">allowlist</span><span class="chipbtn dim">open doc</span></div>') +
      staleCard('stale-1', 'tree_sitter_language_pack.get_parser', '…workflow.md:69',
        'External package path — will resolve once the <b>dependency layer</b> lands package nodes in the graph.') +
      staleCard('stale-2', 'pull_request_target', 'reference/cli.md:74',
        'GitHub concept formatted as code — allowlist candidate.') +
      '</div>' +
      '<div class="d-foot"><div class="btn primary">Open fix PR</div><div class="btn">Re-run check</div></div>' +
      '</div></div></div>';
  };

  /* ladder — cards from the approved ViewLadder board; deadcode-zero animates
     the promotion recorded in assets/out-ladder.jsonl */
  VIEWS.ladder = function () {
    function bars(list) {
      return '<div class="bar-strip">' + list.map(function (c) { return '<div class="' + c + '"></div>'; }).join('') + '</div>';
    }
    var ghost15 = [];
    for (var i = 0; i < 15; i++) ghost15.push('ghost');

    var cards =
      '<div class="inv-card"><div class="name">impact-on-pr</div>' +
      '<div class="chips"><span class="level-chip filled">COMMENT</span><span class="inv-note">ceiling: comment</span></div>' +
      bars(['ok', 'ok', 'ok h96', 'ok', 'ok h58', 'ok', 'ok']) +
      '<div class="inv-caption">7 runs · min 0.56 (grounding fix) · at ceiling</div></div>' +

      '<div class="inv-card"><div class="name">atlas-freshness</div>' +
      '<div class="chips"><span class="level-chip">REPORT</span><span class="inv-note rust">9 clean of 15 → propose</span></div>' +
      bars(['ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ghost', 'ghost', 'ghost', 'ghost', 'ghost', 'ghost']) +
      '<div class="inv-caption">streak 9 — six more clean runs to promotion</div></div>' +

      '<div class="inv-card" id="dz-card"><div class="name">deadcode-zero</div>' +
      '<div class="chips"><span class="level-chip" id="dz-chip">REPORT</span><span class="inv-note" id="dz-note">ceiling: propose</span></div>' +
      '<div class="bar-strip" id="dz-bars">' + ghost15.map(function (c) { return '<div class="' + c + '"></div>'; }).join('') + '</div>' +
      '<div class="inv-caption" id="dz-cap">0 of 15 clean runs ≥ 0.9 · deterministic (no LLM claims)</div></div>' +

      '<div class="inv-card demoted"><div class="name">docs-drift</div>' +
      '<div class="chips"><span class="level-chip down">↓ REPORT</span><span class="inv-note drop">demoted 08-18</span></div>' +
      bars(['ok', 'ok', 'bad h42', 'bad h38', 'bad h45']) +
      '<div class="inv-caption">3 of last 5 below 0.8 — false-positive storm (vendor docs)</div></div>';

    function row(cls, when, inv, type, typeCls, detail) {
      return '<div class="ledger-line ' + cls + '"><span class="when">' + when + '</span><span class="inv">' + inv +
        '</span><span class="type ' + typeCls + '">' + type + '</span><span class="detail">' + detail + '</span></div>';
    }
    var ledger =
      row('', '08-18 17:59', 'impact-on-pr', 'run ✓', 'run', 'closure_recall 1.00 · grounding 1.00 · drop_rate 0.00') +
      row('demote-row', '08-18 17:31', 'docs-drift', 'DEMOTE', 'demote', 'comment → report · “3/5 recent runs below 0.8 — demoted”') +
      row('', '08-18 17:24', 'impact-on-pr', 'errored', 'err', 'OverloadedError (529 storm) — <b>not ledger-scored</b>: missing data, not bad quality') +
      row('', '08-18 01:12', 'impact-on-pr', 'run ✓', 'run', 'grounding 0.56 → oracle bug found (abbreviated paths) → fixed same day');

    return '<div class="appview">' + appHeader('LADDER', 'ladder · autonomy earned per invariant') +
      '<div class="ladder-wrap">' +
      '<div class="inv-grid">' + cards + '</div>' +
      '<div class="ledger-card">' +
      '<div class="ledger-head"><div class="k">LEDGER — EVERY DECISION, WITH ITS REASON</div>' +
      '<span class="src">.gusset/ladder.jsonl · committed to the repo</span></div>' +
      '<div class="ledger-body" id="lad-body">' + ledger + '</div>' +
      '<div class="ledger-rules"><span>Promotion: 15 consecutive runs ≥ 0.9</span><span>·</span>' +
      '<span>Demotion: 3 of 5 below 0.8</span><span>·</span>' +
      '<span id="lad-act-rule"><b>ACT is never ladder-granted — humans only, in gusset.toml</b></span></div>' +
      '</div></div></div>';
  };

  /* SKILL.md — text verbatim from design/demo/assets/skill-excerpt.txt */
  VIEWS.skill = function () {
    return '<div class="appview"><div class="skill-doc"><div class="skill-inner">' +
      '<div class="fm">---\nname: gusset\ndescription: &gt;\n  Drive Gusset, the repo custodian: index a repository into a verified code\n  graph, run blast-radius impact analysis before changes, keep architecture\n  docs fresh, find dead code and stale doc references, and install the\n  autonomous mode that reviews PRs. …\n---</div>' +
      '<h1>Gusset — for coding agents</h1>' +
      '<p>Gusset in one sentence: <b>it maintains a graph of provable facts about a repository (every symbol, every call/import/inheritance edge, every package) and runs workflows whose every claim is verified against that graph before you see it.</b></p>' +
      '<p>Why you (an agent) should care: Gusset\'s outputs are <em>trustworthy inputs for your own work</em>. A Gusset impact report is a verified checklist of call sites your edit affects — use it instead of grepping and guessing. Its scores tell you when NOT to trust a run (see Interpreting output).</p>' +
      '<h2>When to reach for it</h2>' +
      '<div class="skill-table">' +
      '<div class="row head"><div>User intent</div><div>Command</div></div>' +
      '<div class="row" id="skill-impact-row"><div>“What does changing X break/affect?”</div><div><code>gusset impact --symbol &lt;qualname&gt;</code> or <code>--diff &lt;git-range&gt;</code></div></div>' +
      '<div class="row"><div>“What does this PR touch?” (before you edit further)</div><div><code>gusset impact --diff origin/main...HEAD</code></div></div>' +
      '<div class="row"><div>“Document the architecture” / onboarding docs</div><div><code>gusset atlas</code></div></div>' +
      '</div>' +
      '</div></div></div>';
  };

  /* ---------- runtime state ----------------------------------------------- */

  var stage, events = [], nextIdx = 0, clock = 0, startWall = 0, playing = false, raf = 0;
  var curPos = { x: 983, y: 892 };
  var termMode = 'shell';

  function term() { return $('#term'); }
  function pinTerm() { var t = term(); if (t) t.scrollTop = t.scrollHeight; }
  function termAppend(html) { var t = term(); if (!t) return; t.insertAdjacentHTML('beforeend', html); pinTerm(); }
  function killCursors() {
    document.querySelectorAll('#term .tcur').forEach(function (c) { c.remove(); });
  }

  function resetStage() {
    stage.innerHTML = STAGE_HTML;
    curPos = { x: 983, y: 892 };
    termMode = 'shell';
  }

  /* ---------- action executors -------------------------------------------- */

  var ACT = {};

  ACT.sceneTitle = function (a) { $('#scene-title').textContent = a[0]; };

  ACT.titleShow = function () {
    ACT.sceneTitle(['01 — Cold open']);
    stage.insertAdjacentHTML('beforeend',
      '<div id="titlecard">' + logoSVG(150) +
      '<div class="tc-name">GUSSET</div>' +
      '<div class="tc-tag">autonomous self-healing repo upkeep</div></div>');
  };
  ACT.titleOut = function () { var t = $('#titlecard'); if (t) t.classList.add('out'); };
  ACT.titleGone = function () { var t = $('#titlecard'); if (t) t.remove(); };

  ACT.windowsIn = function () {
    $('#win-term').classList.remove('offstage');
    $('#win-app').classList.remove('offstage');
  };

  ACT.caption = function (a) {
    var c = $('#caption');
    c.classList.remove('hidden');
    c.innerHTML = '<div class="cap-in">' + a[0] + '</div>';
  };
  ACT.captionHide = function () { $('#caption').classList.add('hidden'); };

  ACT.transStart = function (a) {
    ACT.sceneTitle([a[0] + ' — ' + a[1]]);
    $('#overlay').innerHTML =
      '<div class="wipe"><div class="tc"><div class="tc-num">SCENE ' + a[0] + '</div>' +
      '<div class="tc-title">' + a[1] + '</div><div class="tc-rule"></div></div></div>';
  };
  ACT.transEnd = function () { $('#overlay').innerHTML = ''; };

  /* terminal */
  ACT.termNewCmd = function (a) {
    killCursors();
    termAppend('<div class="tline"><span class="pr">' + a[0] + '</span><span class="cmd"></span><span class="tcur"></span></div>');
  };
  ACT.termChar = function (a) {
    var lines = document.querySelectorAll('#term .cmd');
    var el = lines[lines.length - 1];
    if (el) el.textContent += a[0];
    pinTerm();
  };
  ACT.termEnter = function () { killCursors(); };
  ACT.termLine = function (a) {
    termAppend('<div class="tline out">' + (a[0] === '' ? '&nbsp;' : a[0]) + '</div>');
  };
  ACT.termPrompt = function () {
    killCursors();
    var p = termMode === 'claude' ? '&gt; ' : '$ ';
    termAppend('<div class="tline"><span class="pr">' + p + '</span><span class="tcur"></span></div>');
  };
  ACT.termClear = function (a) {
    var t = term();
    t.innerHTML = '';
    if (a[0] === 'claude') { t.classList.add('claude'); termMode = 'claude'; }
    else { t.classList.remove('claude'); termMode = 'shell'; }
  };
  ACT.termTitle = function (a) { $('#term-name').textContent = a[0]; };

  /* app window */
  ACT.showApp = function (a) {
    $('#app').innerHTML = VIEWS[a[0]]();
    $('#app-name').textContent = VIEW_TITLES[a[0]];
  };

  ACT.scrollApp = function (a) {
    var el = $('#pr-scroll');
    if (!el) return;
    el.style.transitionDuration = (a[1] || 1500) + 'ms';
    el.style.transform = 'translateY(' + a[0] + 'px)';
  };

  /* cursor */
  ACT.move = function (a) {
    var x, y, ms;
    if (typeof a[0] === 'string') {
      var el = document.querySelector(a[0]);
      if (!el) return;
      var r = el.getBoundingClientRect();
      var s = stage.getBoundingClientRect();
      x = r.left - s.left + r.width / 2 + (a[2] || 0);
      y = r.top - s.top + r.height / 2 + (a[3] || 0);
      ms = a[1] == null ? 800 : a[1];
    } else {
      x = a[0]; y = a[1]; ms = a[2] == null ? 800 : a[2];
    }
    var cur = $('#cursor');
    cur.style.transitionDuration = ms + 'ms';
    cur.style.transform = 'translate(' + (x - 3) + 'px,' + (y - 2) + 'px)';
    curPos = { x: x, y: y };
  };

  ACT.clickDown = function () {
    $('#cursor').classList.add('pressing');
    stage.insertAdjacentHTML('beforeend',
      '<div class="pulse" data-pulse style="left:' + curPos.x + 'px;top:' + curPos.y + 'px"></div>');
  };
  ACT.clickUp = function () { $('#cursor').classList.remove('pressing'); };
  ACT.pulseGone = function () {
    document.querySelectorAll('[data-pulse]').forEach(function (p) { p.remove(); });
  };

  ACT.hlOn = function (a) {
    var el = document.querySelector(a[0]);
    if (el) el.classList.add('demo-hl');
  };
  ACT.hlOff = function (a) {
    var el = document.querySelector(a[0]);
    if (el) el.classList.remove('demo-hl');
  };

  /* impact run animation */
  ACT.impSeed = function () {
    var g = $('#imp-nodes');
    if (!g) return;
    g.insertAdjacentHTML('beforeend',
      '<g class="iseed"><circle cx="' + IMP_C.x + '" cy="' + IMP_C.y + '" r="15" fill="#b4551e"/>' +
      '<text x="' + IMP_C.x + '" y="' + (IMP_C.y + 38) + '" text-anchor="middle" font-family="Spline Sans Mono" ' +
      'font-size="11.5" fill="#b4551e" font-weight="500">serve.events.RunLog.sessions</text></g>');
  };

  ACT.impNode = function (a) {
    var i = a[0];
    var g = $('#imp-nodes');
    if (!g) return;
    var n = IMP_NODES[i], p = impPos(n);
    g.insertAdjacentHTML('beforeend',
      '<g class="inode"><path d="M' + IMP_C.x + ' ' + IMP_C.y + ' L' + p.x.toFixed(1) + ' ' + p.y.toFixed(1) +
      '" stroke="#b4551e" stroke-width="2"/>' +
      '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="10" fill="#fdfcf8" stroke="#2e7d4f" stroke-width="2.2"/>' +
      '<text x="' + (p.x + n.dx).toFixed(1) + '" y="' + (p.y + n.dy).toFixed(1) + '" text-anchor="' + n.anchor +
      '" font-family="Spline Sans Mono" font-size="9.5" fill="#22211d">' + n.label + '</text></g>');
    var led = $('#imp-ledger');
    if (led) {
      led.insertAdjacentHTML('beforeend',
        '<div class="ledger-row"><span class="ok">✓</span><span class="q">' + n.label +
        '</span><span class="via">calls · d1</span></div>');
      led.scrollTop = led.scrollHeight;
    }
    var v = $('#st-ver');
    if (v) v.textContent = String(i + 1);
  };

  ACT.impBad = function () {
    var g = $('#imp-nodes');
    if (!g) return;
    g.insertAdjacentHTML('beforeend',
      '<path id="imp-bad-edge" d="M' + IMP_C.x + ' ' + IMP_C.y + ' L505 150" stroke="#c23934" stroke-width="1.8" stroke-dasharray="5 4"/>' +
      '<g class="bnode" id="imp-bad-node">' +
      '<circle cx="505" cy="150" r="9" fill="#fbeae9" stroke="#c23934" stroke-width="1.9"/>' +
      '<path d="M500 145 l10 10 M510 145 l-10 10" stroke="#c23934" stroke-width="1.7"/>' +
      '<text x="505" y="176" text-anchor="middle" font-family="Spline Sans Mono" font-size="9" fill="#c23934">probe.tracing.flush_all</text>' +
      '<text class="drop-label" x="505" y="190" text-anchor="middle" font-family="Spline Sans Mono" font-size="9" fill="#c23934">dropped @ gate</text>' +
      '</g>');
    var led = $('#imp-ledger');
    if (led) {
      led.insertAdjacentHTML('beforeend',
        '<div class="ledger-row bad" id="imp-bad-row"><span class="x">✗</span><span class="q">probe.tracing.flush_all' +
        '</span><span class="via">edge not in graph</span></div>');
      led.scrollTop = led.scrollHeight;
    }
  };

  ACT.impDrop = function () {
    var n = $('#imp-bad-node');
    if (n) n.classList.add('gone');
    var e = $('#imp-bad-edge');
    if (e) e.style.opacity = '0.35';
    var row = $('#imp-bad-row');
    if (row) row.classList.add('struck');
    var d = $('#st-drop');
    if (d) d.textContent = '1';
  };

  ACT.impScores = function () {
    function set(id, w, color, val) {
      var bar = $('#' + id), v = $('#' + id + 'v');
      if (bar) { bar.style.width = w; bar.style.background = color; }
      if (v) { v.textContent = val; v.style.color = color; }
    }
    set('sc-cr', '100%', '#2e7d4f', '1.00');
    set('sc-sg', '100%', '#2e7d4f', '1.00');
    set('sc-gd', '11%', '#c23934', '0.11');
    var v = $('#sc-gdv');
    if (v) v.style.color = '#6b675c';
  };

  /* drift allowlist interaction */
  ACT.driftAllow = function () {
    var card = $('#stale-0');
    if (card) card.classList.add('leaving');
    var teth = $('#teth-0');
    if (teth) teth.classList.add('allowed');
    var pill = $('#pill-stale');
    if (pill) { pill.textContent = '2 stale'; }
    var dp = $('#drift-pill');
    if (dp && !$('#pill-allow')) {
      dp.insertAdjacentHTML('beforeend', '<span class="g" id="pill-allow">1 allowlisted</span>');
    }
    var da = $('#docA-sub');
    if (da) da.textContent = '2 refs · 1 stale';
    var app = $('#app');
    if (app && !$('#drift-toast')) {
      app.insertAdjacentHTML('beforeend',
        '<div class="app-toast" id="drift-toast">allowlisted <b>asyncio.to_thread</b> — written to gusset.toml</div>');
    }
  };
  ACT.driftAllowGone = function () { var c = $('#stale-0'); if (c) c.style.display = 'none'; };
  ACT.toastHide = function () { var t = $('#drift-toast'); if (t) t.remove(); };

  /* ladder promotion */
  ACT.ladFill = function (a) {
    var i = a[0];
    var bars = $('#dz-bars');
    if (!bars || !bars.children[i]) return;
    bars.children[i].className = 'ok';
    var cap = $('#dz-cap');
    if (cap) cap.textContent = (i + 1) + ' of 15 clean runs ≥ 0.9 · deadcode_precision 1.0';
  };

  ACT.ladPromote = function () {
    var chip = $('#dz-chip');
    if (chip) { chip.textContent = 'COMMENT'; chip.className = 'level-chip promoted'; }
    var note = $('#dz-note');
    if (note) { note.textContent = 'promoted 08-18 · 15 consecutive runs >= 0.9'; note.className = 'inv-note pass'; }
    var cap = $('#dz-cap');
    if (cap) cap.textContent = 'promotion recorded in .gusset/ladder.jsonl';
    var body = $('#lad-body');
    if (body) {
      body.insertAdjacentHTML('afterbegin',
        '<div class="ledger-line promote-row"><span class="when">08-18 20:49</span><span class="inv">deadcode-zero</span>' +
        '<span class="type promote">PROMOTE</span><span class="detail">report → comment · “15 consecutive runs &gt;= 0.9”</span></div>');
    }
  };

  /* close scene */
  ACT.shrinkWins = function () {
    $('#win-term').classList.add('shrunk');
    $('#win-app').classList.add('shrunk');
  };
  ACT.closeCard = function () {
    stage.insertAdjacentHTML('beforeend',
      '<div id="closecard">' + logoSVG(140) +
      '<div class="cc-name">GUSSET</div>' +
      '<div class="cc-tag">Autonomous self-healing repo upkeep.</div>' +
      '<div class="cc-rule"></div>' +
      '<div class="cc-repo">github.com/latchkey-dev/gusset</div></div>');
  };

  /* ---------- expanders: multi-event steps -------------------------------- */

  var EXPAND = {
    termCmd: function (evs, t, args) {
      var text = args[0], ms = args[1], prompt = args[2] || '$ ';
      evs.push({ t: t, name: 'termNewCmd', args: [prompt] });
      for (var i = 0; i < text.length; i++) {
        evs.push({ t: t + 140 + i * ms, name: 'termChar', args: [text[i]] });
      }
      evs.push({ t: t + 140 + text.length * ms + 220, name: 'termEnter', args: [] });
    },
    termOut: function (evs, t, args) {
      var lines = args[0], stagger = args[1] == null ? 380 : args[1];
      lines.forEach(function (l, i) {
        evs.push({ t: t + i * stagger, name: 'termLine', args: [l] });
      });
    },
    transition: function (evs, t, args) {
      evs.push({ t: t, name: 'transStart', args: args });
      evs.push({ t: t + 1200, name: 'transEnd', args: [] });
    },
    titlecard: function (evs, t, args) {
      var dur = args[0] || 7500;
      evs.push({ t: t, name: 'titleShow', args: [] });
      evs.push({ t: t + dur - 900, name: 'titleOut', args: [] });
      evs.push({ t: t + dur, name: 'titleGone', args: [] });
    },
    click: function (evs, t) {
      evs.push({ t: t, name: 'clickDown', args: [] });
      evs.push({ t: t + 150, name: 'clickUp', args: [] });
      evs.push({ t: t + 750, name: 'pulseGone', args: [] });
    },
    highlight: function (evs, t, args) {
      evs.push({ t: t, name: 'hlOn', args: [args[0]] });
      evs.push({ t: t + (args[1] || 2200), name: 'hlOff', args: [args[0]] });
    },
    driftAllow: function (evs, t) {
      evs.push({ t: t, name: 'driftAllow', args: [] });
      evs.push({ t: t + 520, name: 'driftAllowGone', args: [] });
      evs.push({ t: t + 3400, name: 'toastHide', args: [] });
    },
    ladderRun: function (evs, t, args) {
      var n = args[0], stagger = args[1];
      for (var i = 0; i < n; i++) {
        evs.push({ t: t + i * stagger, name: 'ladFill', args: [i] });
      }
    }
  };

  /* ---------- compiler ---------------------------------------------------- */

  function compile(scenes) {
    var evs = [];
    var base = 0;
    scenes.forEach(function (sc) {
      sc.steps.forEach(function (step) {
        var t = base + step[0];
        var name = step[1];
        var args = step.slice(2);
        if (EXPAND[name]) EXPAND[name](evs, t, args);
        else evs.push({ t: t, name: name, args: args });
      });
      base += sc.dur;
    });
    evs.forEach(function (e, i) { e.i = i; });
    evs.sort(function (a, b) { return a.t - b.t || a.i - b.i; });
    return { events: evs, dur: base };
  }

  function exec(ev) {
    var fn = ACT[ev.name];
    if (!fn) { throw new Error('unknown demo action: ' + ev.name); }
    fn(ev.args);
  }

  /* ---------- scheduler --------------------------------------------------- */

  function tick(now) {
    clock = now - startWall;
    while (nextIdx < events.length && events[nextIdx].t <= clock) {
      exec(events[nextIdx]);
      nextIdx++;
    }
    if (clock < window.demoDuration + 600) {
      raf = requestAnimationFrame(tick);
    } else {
      playing = false;
    }
  }

  window.demoPlay = function () {
    if (playing) return;
    playing = true;
    stage.classList.remove('no-anim');
    startWall = performance.now() - clock;
    raf = requestAnimationFrame(tick);
  };

  /* Seek rebuilds the stage and instant-applies every event ≤ ms.
     .no-anim stays on while seeked so stills show FINAL states (CSS
     animations would otherwise restart when re-enabled); demoPlay lifts it. */
  window.demoSeek = function (ms) {
    if (raf) cancelAnimationFrame(raf);
    playing = false;
    resetStage();
    stage.classList.add('no-anim');
    nextIdx = 0;
    while (nextIdx < events.length && events[nextIdx].t <= ms) {
      exec(events[nextIdx]);
      nextIdx++;
    }
    clock = ms;
    void stage.offsetHeight; /* force reflow so styles commit */
    pinTerm();
  };

  /* ---------- boot -------------------------------------------------------- */

  document.addEventListener('DOMContentLoaded', function () {
    stage = document.getElementById('stage');
    var compiled = compile(window.DEMO_SCENES);
    events = compiled.events;
    window.demoDuration = compiled.dur;
    resetStage();
    if (/[?&]play=1/.test(location.search)) {
      var start = function () { window.demoPlay(); };
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(start);
      else start();
    }
  });
})();
