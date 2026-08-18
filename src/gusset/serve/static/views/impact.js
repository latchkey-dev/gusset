// #/impact — blast-radius replay of an impact run (ViewImpact mockup).

import { el, svg, getJSON, codeBox, emptyState, fmtScore } from "../util.js";

const VB_W = 860, VB_H = 690;
const CX = VB_W / 2, CY = 330;

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
        ? "serve is read-only for LLM runs — run this from your terminal, then reload to replay it claim by claim."
        : "Run an impact analysis and this view replays it — every ring, every claim, every drop.",
      cmd,
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
    svgEl.append(svg("text", {
      x: lx - 2, y: ly - 6, "font-family": "Spline Sans Mono, monospace",
      "font-size": 10, fill: "var(--faint)",
    }, `DEPTH ${d}`));
  }

  const edgesG = svg("g");
  const nodesG = svg("g");
  const labelsG = svg("g");
  svgEl.append(edgesG, nodesG, labelsG);

  // -- reveal machinery (replay scrubber) ------------------------------------
  function render(revealV, revealD) {
    edgesG.textContent = ""; nodesG.textContent = ""; labelsG.textContent = "";
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
    // seeds
    seeds.forEach((q) => {
      const p = pos.get(q);
      nodesG.append(svg("circle", { cx: p.x, cy: p.y, r: 15, fill: "var(--rust)" }));
      labelsG.append(svg("text", {
        x: p.x, y: p.y + 34, "text-anchor": "middle",
        "font-family": "Spline Sans Mono, monospace", "font-size": 11.5,
        "font-weight": 500, fill: "var(--rust)",
      }, shortName(q)));
    });
    for (const c of shownV) {
      const p = pos.get(c.qualname);
      const r = c.depth === 1 ? 11 : 9;
      nodesG.append(svg("circle", {
        cx: p.x, cy: p.y, r, fill: "var(--panel)",
        stroke: "var(--pass)", "stroke-width": c.depth === 1 ? 2.2 : 1.9,
      }));
      const below = p.y >= CY;
      labelsG.append(svg("text", {
        x: p.x, y: below ? p.y + r + 13 : p.y - r - 9, "text-anchor": "middle",
        "font-family": "Spline Sans Mono, monospace", "font-size": 9.5, fill: "var(--ink)",
      }, shortName(c.qualname)));
    }
    for (const c of shownD) {
      const p = pos.get(c.qualname);
      const g = svg("g", { opacity: 0.75 });
      g.append(
        svg("circle", { cx: p.x, cy: p.y, r: 9, fill: "var(--drop-tint)", stroke: "var(--drop)", "stroke-width": 1.9 }),
        svg("path", { d: `M${p.x - 5} ${p.y - 5} l10 10 M${p.x + 5} ${p.y - 5} l-10 10`, stroke: "var(--drop)", "stroke-width": 1.7 }),
      );
      nodesG.append(g);
      labelsG.append(svg("text", {
        x: p.x, y: p.y + 24, "text-anchor": "middle",
        "font-family": "Spline Sans Mono, monospace", "font-size": 9, fill: "var(--drop)",
      }, "dropped @ gate"));
    }
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
    svgEl, el("div", { class: "overlay-chips" }, el("span", { class: "chip dim" }, "RUN"), picker), replayBar);

  // -- right panel -----------------------------------------------------------
  const scoreRows = [];
  const scores = model.scores || {};
  for (const [name, value] of Object.entries(scores)) {
    const isDropRate = name.includes("drop");
    const good = isDropRate ? value <= 0.2 : value >= 0.8;
    const barColor = isDropRate ? "var(--drop)" : (good ? "var(--pass)" : "var(--rust)");
    const valColor = isDropRate ? "var(--muted)" : barColor;
    scoreRows.push(el("div", { class: "score-row" },
      el("span", { class: "name", title: name }, name),
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
      el("div", { class: "k" }, "SEEDS"),
      seeds.length
        ? seeds.map((q) => el("span", { style: { fontFamily: "var(--mono)", fontSize: "12px", color: "var(--rust)", wordBreak: "break-all" } }, q))
        : el("span", { style: { fontFamily: "var(--mono)", fontSize: "12px", color: "var(--faint)" } }, "—"),
      el("div", { style: { fontSize: "11.5px", color: "var(--muted)" } },
        `graph @ ${ctx.commit || "?"}`),
      seedBits),
    el("div", { class: "stat3" },
      el("div", { class: "verified" }, el("div", { class: "n" }, String(verified.length)), el("div", { class: "l" }, "VERIFIED")),
      el("div", { class: "dropped" }, el("div", { class: "n" }, String(dropped.length)), el("div", { class: "l" }, "DROPPED")),
      el("div", { class: "rings" }, el("div", { class: "n" }, String(model.rings || 0)), el("div", { class: "l" }, "RINGS"))),
    el("div", { style: { display: "flex", flexDirection: "column", gap: "7px" } },
      el("div", { class: "k" }, "ORACLE SCORES"), scoreRows),
    el("div", { style: { flex: "1", display: "flex", flexDirection: "column", gap: "6px", minHeight: "0" } },
      el("div", { class: "k" }, "CLAIM LEDGER"),
      ledger,
      el("div", { class: "footnote" }, "Every row carries its edge; drops are logged, never hidden.")),
  );

  container.append(el("div", { class: "view3" }, stage, right));
  applyTurn(turns.length);

  return () => stopPlay();
}

function shortName(qualname) {
  const parts = String(qualname).split(".");
  return parts.length <= 3 ? qualname : parts.slice(-3).join(".");
}
