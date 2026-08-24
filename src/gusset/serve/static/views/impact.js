// #/impact — blast-radius replay of an impact run (ViewImpact mockup).

import { el, svg, getJSON, codeBox, emptyState, explainer, fmtScore } from "../util.js";

function impactHelp() {
  return explainer(
        "If you changed the thing in the middle, this is what else could break.",
        "Each ring is one step further away. Ring 1 uses it directly, ring 2 uses something in ring 1, and so on.",
        "Green means Gusset found the connection in your actual code. Red means the model suggested it, the code didn\u2019t back it up, and it was thrown away \u2014 those are shown rather than hidden so you can see what was rejected.",
        "This is the same list that gets posted as the pull-request comment.",
      );
}

const VB_W = 860, VB_H = 690;
const CX = VB_W / 2, CY = 330;
const CROWDED_RING = 10; // above this many nodes a ring goes hover-only

// text measurement for label pills (viewBox units == CSS px here)
const measure = (() => {
  const c = document.createElement("canvas").getContext("2d");
  return (text, size, weight = 400) => {
    c.font = `${weight} ${size}px "Spline Sans Mono", monospace`;
    return c.measureText(text).width;
  };
})();

const boxesOverlap = (a, b, m = 2) =>
  a.x < b.x + b.w + m && b.x < a.x + a.w + m
  && a.y < b.y + b.h + m && b.y < a.y + a.h + m;

export async function mountImpact(container, params, ctx) {
  const seed = params.get("seed");
  let runs = [];
  try { runs = (await getJSON("/api/runs")).filter((r) => r.workflow === "impact"); }
  catch { runs = []; }

  if (runs.length === 0) {
    const cmd = `gusset impact --symbol ${seed || "<your.symbol>"}`;
    const wrap = emptyState(
      seed ? "Run impact from your terminal" : "No impact runs yet",
      seed
        ? "This page can\u2019t start a run itself \u2014 anything that calls a model happens in your terminal, so you stay in control of what gets spent. Run this and the page follows along live."
        : "Ask what a change would affect, and this page replays the answer \u2014 what was checked, what was confirmed, and what was rejected.",
      cmd,
      impactHelp(),
    );
    container.append(wrap);
    ctx.setHeader("impact · no runs yet");
    return;
  }

  const runId = params.get("id") && runs.some((r) => r.session_id === params.get("id"))
    ? params.get("id")
    : runs[0].session_id;
  const model = await getJSON(`/api/impact?id=${encodeURIComponent(runId)}`);
  ctx.setHeader(`impact · session ${runId}`);
  ctx.session = runId; // the heartbeat routes this session's events to us

  const verified = model.verified || [];
  const dropped = model.dropped || [];
  const seeds = model.seeds || [];
  const rings = Math.max(1, model.rings || 1);
  const turns = model.turns || [];

  // -- geometry --------------------------------------------------------------
  const ringR = (d) => d * (235 / Math.max(2, rings));
  const pos = new Map(); // qualname -> {x, y, angle}
  seeds.forEach((q, i) => {
    const off = seeds.length === 1 ? { x: 0, y: 0 }
      : { x: 34 * Math.cos((i / seeds.length) * 2 * Math.PI), y: 34 * Math.sin((i / seeds.length) * 2 * Math.PI) };
    pos.set(q, { x: CX + off.x, y: CY + off.y, angle: 0 });
  });
  const byDepth = new Map();
  for (const c of verified) {
    if (!byDepth.has(c.depth)) byDepth.set(c.depth, []);
    byDepth.get(c.depth).push(c);
  }
  for (const d of [...byDepth.keys()].sort((a, b) => a - b)) {
    const ring = byDepth.get(d);
    ring.forEach((c, i) => {
      const parent = pos.get(c.via);
      let angle;
      if (d === 1 || !parent) {
        angle = -Math.PI / 2 + (i / ring.length) * 2 * Math.PI + 0.35;
      } else {
        const sibs = ring.filter((x) => x.via === c.via);
        const j = sibs.indexOf(c);
        angle = parent.angle + (j - (sibs.length - 1) / 2) * (0.9 / d);
      }
      const r = ringR(d);
      pos.set(c.qualname, { x: CX + r * Math.cos(angle), y: CY + r * Math.sin(angle), angle });
    });
  }
  dropped.forEach((c, i) => {
    const parent = pos.get(c.via) || { angle: 0.3 + i };
    const angle = (pos.get(c.via) && c.via !== seeds[0]) ? parent.angle + 0.35 : 0.12 + i * 0.8;
    const r = ringR(rings) + 48;
    pos.set(c.qualname, { x: CX + r * Math.cos(angle), y: CY + r * Math.sin(angle), angle });
  });

  // -- svg -------------------------------------------------------------------
  const svgEl = svg("svg", {
    class: "impact-svg", viewBox: `0 0 ${VB_W} ${VB_H}`,
    preserveAspectRatio: "xMidYMid meet", fill: "none",
  });

  // depth rings + labels (outermost dashed, inner solid — mockup)
  const ringObstacles = []; // DEPTH n texts — node labels must not cover them
  for (let d = 1; d <= rings; d++) {
    const r = ringR(d);
    const outer = d === rings && rings > 1;
    svgEl.append(svg("circle", {
      cx: CX, cy: CY, r,
      stroke: outer ? "var(--faint)" : "var(--ink)",
      "stroke-width": outer ? 1.3 : 1.6,
      ...(outer ? { "stroke-dasharray": "6 7" } : {}),
    }));
    const lx = CX - r * 0.707, ly = CY - r * 0.707;
    ringObstacles.push({
      d, x: lx - 2, y: ly - 16, w: measure(`DEPTH ${d}`, 10) + 4, h: 13,
      tx: lx - 2, ty: ly - 6,
    });
  }

  const edgesG = svg("g");
  const nodesG = svg("g");
  const ringLabelsG = svg("g"); // above nodes so a node never buries "DEPTH n"
  const labelsG = svg("g");
  const hoverG = svg("g", { "pointer-events": "none" });
  svgEl.append(edgesG, nodesG, ringLabelsG, labelsG, hoverG);
  for (const o of ringObstacles) {
    ringLabelsG.append(svg("text", {
      x: o.tx, y: o.ty, "font-family": "Spline Sans Mono, monospace",
      "font-size": 10, fill: "var(--faint)",
      stroke: "var(--panel)", "stroke-width": 5, "paint-order": "stroke",
    }, `DEPTH ${o.d}`));
  }

  // -- label pills -----------------------------------------------------------
  // Placement: radially outside the node relative to center (left half
  // anchors right edge, right half anchors left edge), then a greedy
  // vertical nudge away from center until no two boxes overlap. The seed
  // label is placed first and painted last, so it is never overdrawn.

  function labelSpec(text, p, r, { size = 10, color = "var(--ink)", weight = 400 } = {}) {
    const dx = p.x - CX, dy = p.y - CY;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / d, uy = dy / d;
    const gap = r + 8;
    const bx = p.x + ux * gap, by = p.y + uy * gap;
    const w = measure(text, size, weight) + 10;
    const h = size + 7;
    let box;
    if (Math.abs(ux) < 0.25) {
      // nearly vertical: center the pill above/below the node
      box = { x: p.x - w / 2, y: uy < 0 ? by - h : by, w, h };
    } else if (ux < 0) {
      box = { x: bx - w, y: by - h / 2, w, h }; // left half → right-aligned
    } else {
      box = { x: bx, y: by - h / 2, w, h };     // right half → left-aligned
    }
    box.x = Math.max(3, Math.min(VB_W - 3 - w, box.x)); // stay in frame
    return { text, box, size, color, weight, dir: p.y < CY ? -1 : 1 };
  }

  function nudge(spec, placed) {
    for (let i = 0; i < 60; i++) {
      const hit = placed.find((b) => boxesOverlap(spec.box, b));
      if (!hit) break;
      spec.box.y = spec.dir < 0
        ? hit.y - spec.box.h - 3
        : hit.y + hit.h + 3;
    }
    placed.push(spec.box);
  }

  function paintLabel(spec) {
    const { box, text, size, color, weight } = spec;
    return svg("g", { class: "lbl" },
      svg("rect", {
        x: box.x, y: box.y, width: box.w, height: box.h, rx: 3,
        fill: "var(--panel)", stroke: "var(--line)", "stroke-width": 1,
      }),
      svg("text", {
        x: box.x + box.w / 2, y: box.y + box.h / 2 + size * 0.36,
        "text-anchor": "middle", "font-family": "Spline Sans Mono, monospace",
        "font-size": size, "font-weight": weight, fill: color,
      }, text));
  }

  function hoverLabel(c) {
    hoverG.textContent = "";
    const p = pos.get(c.qualname);
    if (!p) return;
    const spec = labelSpec(shortName(c.qualname), p, 12, { size: 10 });
    hoverG.append(paintLabel(spec));
  }

  // -- reveal machinery (replay scrubber) ------------------------------------
  function render(revealV, revealD) {
    edgesG.textContent = ""; nodesG.textContent = ""; labelsG.textContent = "";
    hoverG.textContent = "";
    const shownV = verified.slice(0, revealV);
    const shownD = dropped.slice(0, revealD);
    const shownSet = new Set([...seeds, ...shownV.map((c) => c.qualname)]);

    for (const c of shownV) {
      const p = pos.get(c.via && shownSet.has(c.via) ? c.via : seeds[0]) || { x: CX, y: CY };
      const q = pos.get(c.qualname);
      edgesG.append(svg("path", {
        d: `M${p.x} ${p.y} L${q.x} ${q.y}`,
        stroke: "var(--rust)", "stroke-width": c.depth === 1 ? 2.2 : 1.7,
      }));
    }
    for (const c of shownD) {
      const p = pos.get(c.via) || pos.get(seeds[0]) || { x: CX, y: CY };
      const q = pos.get(c.qualname);
      edgesG.append(svg("path", {
        d: `M${p.x} ${p.y} L${q.x} ${q.y}`,
        stroke: "var(--drop)", "stroke-width": 1.8, "stroke-dasharray": "5 4",
      }));
    }

    // label layout: seed boxes claim their space first
    const placed = [...ringObstacles];
    const seedSpecs = seeds.map((q) => {
      const p = pos.get(q);
      const text = shortName(q);
      const w = measure(text, 11.5, 500) + 12;
      const h = 19;
      const spec = {
        text, size: 11.5, weight: 500, color: "var(--rust)", dir: 1,
        box: { x: p.x - w / 2, y: p.y + 22, w, h },
      };
      nudge(spec, placed);
      return spec;
    });

    const ringCount = new Map();
    for (const c of shownV) ringCount.set(c.depth, (ringCount.get(c.depth) || 0) + 1);

    // seeds (nodes now, labels last so nothing overdraws them)
    seeds.forEach((q) => {
      const p = pos.get(q);
      nodesG.append(svg("circle", { cx: p.x, cy: p.y, r: 15, fill: "var(--rust)" }));
    });
    for (const c of shownV) {
      const p = pos.get(c.qualname);
      const r = c.depth === 1 ? 11 : 9;
      const node = svg("circle", {
        cx: p.x, cy: p.y, r, fill: "var(--panel)",
        stroke: "var(--pass)", "stroke-width": c.depth === 1 ? 2.2 : 1.9,
      });
      nodesG.append(node);
      if ((ringCount.get(c.depth) || 0) > CROWDED_RING) {
        // crowded ring: label on hover only
        node.addEventListener("mouseenter", () => hoverLabel(c));
        node.addEventListener("mouseleave", () => { hoverG.textContent = ""; });
      } else {
        const spec = labelSpec(shortName(c.qualname), p, r, { size: 10 });
        nudge(spec, placed);
        labelsG.append(paintLabel(spec));
      }
    }
    for (const c of shownD) {
      const p = pos.get(c.qualname);
      const g = svg("g", { opacity: 0.85 });
      g.append(
        svg("circle", { cx: p.x, cy: p.y, r: 9, fill: "var(--drop-tint)", stroke: "var(--drop)", "stroke-width": 1.9 }),
        svg("path", { d: `M${p.x - 5} ${p.y - 5} l10 10 M${p.x + 5} ${p.y - 5} l-10 10`, stroke: "var(--drop)", "stroke-width": 1.7 }),
      );
      nodesG.append(g);
      const spec = labelSpec("dropped @ gate", p, 9, { size: 9.5, color: "var(--drop)" });
      nudge(spec, placed);
      labelsG.append(paintLabel(spec));
    }
    for (const spec of seedSpecs) labelsG.append(paintLabel(spec));

    const shownRings = shownV.reduce((m, c) => Math.max(m, c.depth), 0);
    ringLabel.textContent = `ring ${shownRings} / ${rings}`;
  }

  const scrub = el("input", { class: "scrub", type: "range", min: "0", max: String(turns.length), step: "1" });
  scrub.value = String(turns.length);
  const ringLabel = el("span", { class: "ring-label" });
  let playTimer = null;

  function applyTurn(t) {
    // turn t (1-based) reveals the cumulative verified_n/dropped_n at that turn
    if (t <= 0) { render(0, 0); return; }
    const turn = turns[Math.min(t, turns.length) - 1];
    render(turn.verified_n ?? verified.length, turn.dropped_n ?? dropped.length);
  }

  scrub.addEventListener("input", () => { stopPlay(); applyTurn(Number(scrub.value)); });

  function stopPlay() { if (playTimer) { clearInterval(playTimer); playTimer = null; } }

  const playBtn = el("button", {
    title: "replay from the start",
    style: { display: "flex", alignItems: "center" },
    onclick: () => {
      stopPlay();
      let t = 0;
      scrub.value = "0"; applyTurn(0);
      playTimer = setInterval(() => {
        t += 1;
        scrub.value = String(t); applyTurn(t);
        if (t >= turns.length) stopPlay();
      }, 650);
    },
  });
  playBtn.append(svg("svg", { width: 14, height: 14, viewBox: "0 0 20 20", fill: "none" },
    svg("path", { d: "M6 4 L15 10 L6 16 Z", fill: "var(--ink)" })));

  const replayBar = el("div", { class: "replay-bar" },
    playBtn, el("span", { class: "mono-label" }, "replay"), scrub, ringLabel);

  // -- run picker ------------------------------------------------------------
  const picker = el("select", { class: "chip" });
  for (const r of runs) {
    picker.append(el("option", { value: r.session_id, selected: r.session_id === runId }, r.session_id));
  }
  picker.addEventListener("change", () => {
    const q = seed ? `&seed=${encodeURIComponent(seed)}` : "";
    location.hash = `#/impact?id=${encodeURIComponent(picker.value)}${q}`;
  });

  const stage = el("div", { class: "stage dotbg" },
    svgEl,
    el("div", { class: "overlay-chips" },
      el("span", { class: "chip dim" }, "RUN"), picker,
      impactHelp()),
    replayBar);

  // -- right panel -----------------------------------------------------------
  // The metric names are the product's vocabulary and appear in CI output
  // and the docs, so they stay — but nobody should have to look them up to
  // read this panel.
  const SCORE_HELP = {
    closure_recall:
      "Of everything your code says could be affected, how much did this run "
      + "actually find? 1.00 means it missed nothing.",
    gate_drop_rate:
      "How much of what the model claimed got thrown out for not matching "
      + "your code. 0.00 means nothing had to be rejected.",
    summary_grounding:
      "Of the things named in the written summary, how many really exist in "
      + "your code. 1.00 means it invented nothing.",
    module_coverage:
      "How much of the codebase the write-up actually covers.",
  };
  const scoreRows = [];
  const scores = model.scores || {};
  for (const [name, value] of Object.entries(scores)) {
    const isDropRate = name.includes("drop");
    const good = isDropRate ? value <= 0.2 : value >= 0.8;
    const barColor = isDropRate ? "var(--drop)" : (good ? "var(--pass)" : "var(--rust)");
    const valColor = isDropRate ? "var(--muted)" : barColor;
    scoreRows.push(el("div", { class: "score-row" },
      el("span", { class: "name", title: SCORE_HELP[name] || name }, name),
      el("div", { class: "bar" }, el("div", { style: { width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`, background: barColor } })),
      el("span", { class: "val", style: { color: valColor } }, fmtScore(value)),
    ));
  }
  if (scoreRows.length === 0) {
    scoreRows.push(el("div", { class: "footnote" },
      model.outcome === "running" ? "run still in flight — no scores yet" : "no scores recorded"));
  }

  const ledgerRows = [...verified.map((c) => ({ c, ok: true })), ...dropped.map((c) => ({ c, ok: false }))]
    .sort((a, b) => (a.c.depth - b.c.depth) || (a.ok === b.ok ? 0 : a.ok ? -1 : 1));
  const ledger = el("div", { class: "ledger-box" });
  for (const { c, ok } of ledgerRows) {
    ledger.append(el("div", { class: ok ? "ledger-row" : "ledger-row bad" },
      el("span", { style: { color: ok ? "var(--pass)" : "var(--drop)", flex: "none" } }, ok ? "✓" : "✗"),
      el("span", { class: "q", title: c.qualname }, c.qualname),
      el("span", { class: "via" }, ok ? `${c.edge_kind || "edge"} · d${c.depth}` : (c.reason || c.why || "dropped")),
    ));
  }
  if (ledgerRows.length === 0) {
    ledger.append(el("div", { class: "ledger-row" },
      el("span", { class: "q" }, "no claims yet")));
  }

  const seedBits = [];
  if (seed) {
    seedBits.push(
      el("div", { class: "footnote" }, "serve is read-only for LLM runs — run from your terminal:"),
      codeBox(`gusset impact --symbol ${seed}`),
    );
  }

  const right = el("div", { class: "side right", style: { width: "360px", overflow: "hidden" } },
    el("div", { style: { display: "flex", flexDirection: "column", gap: "4px" } },
      el("div", { class: "k" }, "IF YOU CHANGE"),
      seeds.length
        ? seeds.map((q) => el("span", { style: { fontFamily: "var(--mono)", fontSize: "12px", color: "var(--rust)", wordBreak: "break-all" } }, q))
        : el("span", { style: { fontFamily: "var(--mono)", fontSize: "12px", color: "var(--faint)" } }, "—"),
      el("div", { style: { fontSize: "11.5px", color: "var(--muted)" } },
        `graph @ ${ctx.commit || "?"}`),
      seedBits),
    el("div", { class: "stat3" },
      el("div", { class: "verified" }, el("div", { class: "n" }, String(verified.length)), el("div", { class: "l" }, "CONFIRMED")),
      el("div", { class: "dropped" }, el("div", { class: "n" }, String(dropped.length)), el("div", { class: "l" }, "REJECTED")),
      el("div", { class: "rings" }, el("div", { class: "n" }, String(model.rings || 0)), el("div", { class: "l" }, "STEPS OUT"))),
    el("div", { style: { display: "flex", flexDirection: "column", gap: "7px" } },
      el("div", { class: "k", title: "Computed from your code, not judged by a model." }, "HOW WELL IT DID"), scoreRows),
    el("div", { style: { flex: "1", display: "flex", flexDirection: "column", gap: "6px", minHeight: "0" } },
      el("div", { class: "k" }, "WHAT COULD BREAK"),
      ledger,
      el("div", { class: "footnote" },
        "Each row names the connection it was proved by. Rejected claims stay on the list rather than disappearing.")),
  );

  container.append(el("div", { class: "view3" }, stage, right));
  applyTurn(turns.length);

  // -- live refresh + poll fallback -----------------------------------------
  // The heartbeat calls ctx.refresh on this session's turn/finish events.
  // The whole view derives from the model, so refresh = remount (coalesced —
  // bursts of turns rebuild once). While the run is in flight a slow poll
  // stays as fallback: 5s while SSE is connected, 2s when it is not.
  let refreshTimer = null;
  ctx.refresh = () => {
    if (refreshTimer) return;
    refreshTimer = setTimeout(() => { refreshTimer = null; ctx.remount(); }, 250);
  };

  let pollTimer = null;
  if (model.outcome === "running") {
    const seen = turns.length + 1; // start + the turns already rendered
    const tick = async () => {
      try {
        if (!document.hidden) {
          const fresh = await getJSON(`/api/run?id=${encodeURIComponent(runId)}&after=${seen}`);
          if (fresh.length) { ctx.refresh(); return; } // remount picks it up
        }
      } catch { /* transient — next tick retries */ }
      pollTimer = setTimeout(tick, ctx.syncConnected?.() ? 5000 : 2000);
    };
    pollTimer = setTimeout(tick, ctx.syncConnected?.() ? 5000 : 2000);
  }

  return () => {
    stopPlay();
    clearTimeout(refreshTimer);
    clearTimeout(pollTimer);
  };
}

function shortName(qualname) {
  const parts = String(qualname).split(".");
  return parts.length <= 3 ? qualname : parts.slice(-3).join(".");
}
