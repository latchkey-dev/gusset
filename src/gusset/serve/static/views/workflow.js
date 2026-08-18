// #/workflow — live DAG + turn feed for a run (ViewWorkflow mockup).
// Note: the impact workflow only fires turn events at verify_gate and
// synthesize; resolve_seeds / expand_ring status is inferred from those.

import { el, svg, getJSON, emptyState, explainer, fmtClock, fmtScore } from "../util.js";

export async function mountWorkflow(container, params, ctx) {
  let runs = [];
  try { runs = await getJSON("/api/runs"); } catch { runs = []; }

  if (runs.length === 0) {
    container.append(emptyState(
      "No runs yet",
      "Start a workflow and this view shows it live — node by node, turn by turn.",
      "gusset impact --symbol <your.symbol>",
    ));
    ctx.setHeader("workflow · no runs yet");
    return;
  }

  const runId = params.get("id") && runs.some((r) => r.session_id === params.get("id"))
    ? params.get("id")
    : runs[0].session_id;
  const workflow = runs.find((r) => r.session_id === runId)?.workflow || "run";

  let events = await getJSON(`/api/run?id=${encodeURIComponent(runId)}`);

  // -- scaffold --------------------------------------------------------------
  const dagHost = el("div");
  const picker = el("select", { class: "chip" });
  for (const r of runs) {
    picker.append(el("option", { value: r.session_id, selected: r.session_id === runId },
      `${r.session_id}${r.outcome === "running" ? " ●" : ""}`));
  }
  picker.addEventListener("change", () => {
    location.hash = `#/workflow?id=${encodeURIComponent(picker.value)}`;
  });

  const stage = el("div", { class: "wf-stage dotbg" },
    el("div", { class: "overlay-chips" },
      el("span", { class: "chip dim" }, "RUN"), picker,
      explainer(
        "The execution graph of a run, as it happened. Each box is a LangGraph node; the guards are code, not model choice.",
        "The feed is the run's turn-by-turn event log.",
      )),
    dagHost);

  const feed = el("div", { class: "wf-feed" });
  const right = el("div", { class: "wf-right" },
    el("div", { class: "wf-feed-head" },
      el("div", { class: "k" }, "TURN FEED"),
      el("div", { class: "wf-session" }, `session ${runId}`)),
    feed,
    el("div", { class: "wf-guards" },
      el("div", { class: "k" }, "GUARDS ACTIVE"),
      el("div", { class: "guard-chips" },
        el("span", {}, "depth ≤ 4"), el("span", {}, "fan-out ≤ 40"),
        el("span", {}, "fallback: sonnet-5"), el("span", {}, "8 retries")),
      el("div", { class: "footnote" }, "Routing is code, not model vibes — these fire deterministically.")),
  );

  container.append(el("div", { class: "view3" }, stage, right));

  // -- derive + render -------------------------------------------------------
  function derive() {
    const start = events.find((e) => e.kind === "start");
    const turns = events.filter((e) => e.kind === "turn");
    const finish = [...events].reverse().find((e) => e.kind === "finish") || null;
    const gates = turns.filter((e) => e.node === "verify_gate");
    const synth = turns.filter((e) => e.node === "synthesize");
    const lastGate = gates[gates.length - 1] || null;
    const lastTurn = turns[turns.length - 1] || null;
    return { start, turns, finish, gates, synth, lastGate, lastTurn };
  }

  function statuses(d) {
    // done | running | pending, per canonical node
    const s = { resolve_seeds: "pending", expand_ring: "pending", verify_gate: "pending", synthesize: "pending", human_gate: "pending" };
    if (d.finish) {
      s.resolve_seeds = s.expand_ring = s.verify_gate = s.synthesize = "done";
      s.human_gate = "done";
      return s;
    }
    if (d.turns.length === 0) { s.resolve_seeds = "running"; return s; }
    s.resolve_seeds = "done";
    if (d.synth.length > 0) {
      s.expand_ring = s.verify_gate = s.synthesize = "done";
      s.human_gate = "running";
      return s;
    }
    // last fired node is verify_gate → loop is either expanding again or moving on
    s.expand_ring = "running";
    s.verify_gate = "done";
    return s;
  }

  function renderAll() {
    const d = derive();
    const s = statuses(d);
    renderDag(dagHost, d, s, workflow);
    renderFeed(feed, d, workflow);
    const live = !d.finish;
    ctx.setLive(live);
    ctx.setHeader(`workflow · ${workflow} ${live ? "running" : (d.finish.outcome || "finished")}`);
    return live;
  }

  let live = renderAll();

  // -- poll while live and visible ------------------------------------------
  let timer = null;
  async function poll() {
    if (document.hidden || !live) return;
    const after = events.length ? events[events.length - 1].seq + 1 : 0;
    try {
      const fresh = await getJSON(`/api/run?id=${encodeURIComponent(runId)}&after=${after}`);
      if (fresh.length) { events = events.concat(fresh); live = renderAll(); }
    } catch { /* transient — next tick retries */ }
    if (!live && timer) { clearInterval(timer); timer = null; }
  }
  if (live) timer = setInterval(poll, 2000);
  const onVis = () => { if (!document.hidden) poll(); };
  document.addEventListener("visibilitychange", onVis);

  return () => {
    if (timer) clearInterval(timer);
    document.removeEventListener("visibilitychange", onVis);
    ctx.setLive(false);
  };
}

// -- DAG ----------------------------------------------------------------------

function boxStyle(status) {
  if (status === "done") return { fill: "var(--pass-tint)", stroke: "var(--pass)", width: 2, dash: null, opacity: 1 };
  if (status === "running") return { fill: "var(--rust-tint)", stroke: "var(--rust)", width: 2.6, dash: null, opacity: 1 };
  return { fill: "var(--panel)", stroke: "var(--faint)", width: 1.6, dash: "6 4", opacity: 0.55 };
}

function renderDag(host, d, s, workflow) {
  host.textContent = "";
  const seeds = d.lastTurn?.seeds || [];
  // impact runs carry seeds/rings; other workflows get generic, honest lines
  const impactish = Array.isArray(d.lastTurn?.seeds);
  const ringsDone = d.lastTurn?.rings_done ?? d.gates.length;
  const verified = d.lastGate?.verified || [];
  const dropped = d.lastGate?.dropped || [];
  const prevGate = d.gates[d.gates.length - 2] || null;
  const passedRing = verified.length - (prevGate?.verified?.length || 0);
  const droppedRing = dropped.length - (prevGate?.dropped?.length || 0);
  const dur = (a, b) => (a && b && b.ts > a.ts) ? ` · ${(b.ts - a.ts).toFixed(1)}s` : "";

  const lines = {
    resolve_seeds: {
      done: [impactish
        ? `✓ ${seeds.length} seed${seeds.length === 1 ? "" : "s"}${dur(d.start, d.turns[0])}`
        : `✓ done${dur(d.start, d.turns[0])}`, null],
      running: [impactish ? "● resolving seeds…" : "● starting…", null],
      pending: ["pending", null],
    },
    expand_ring: {
      done: [impactish
        ? `✓ ${ringsDone} ring${ringsDone === 1 ? "" : "s"} expanded`
        : `✓ ${d.gates.length} turn${d.gates.length === 1 ? "" : "s"}`, null],
      running: [impactish ? `● running · ring ${ringsDone + 1}` : "● running…",
        `${verified.length} verified so far`],
      pending: ["pending", null],
    },
    verify_gate: {
      done: [impactish
        ? `ring ${ringsDone}: ${Math.max(0, passedRing)} passed`
        : `${verified.length} verified`,
      `${Math.max(0, impactish ? droppedRing : dropped.length)} dropped (logged)`],
      running: ["● verifying…", null],
      pending: ["pending", null],
    },
    synthesize: {
      done: ["✓ draft ready", null],
      running: ["● writing draft…", null],
      pending: ["pending", null],
    },
    human_gate: {
      done: [`✓ ${d.finish?.outcome || "finished"}`, null],
      running: ["interrupt · awaits approval", null],
      pending: ["interrupt · awaits approval", null],
    },
  };

  const root = svg("svg", { width: 640, height: 600, viewBox: "0 0 640 600", fill: "none", style: { maxWidth: "100%", maxHeight: "100%" } });

  const conn = (path, on) => svg("path", {
    d: path, stroke: on ? "var(--pass)" : "var(--faint)", "stroke-width": 2,
    ...(on ? {} : { "stroke-dasharray": "5 5" }),
  });
  root.append(
    conn("M320 90 L320 150", s.expand_ring !== "pending"),
    conn("M320 230 L320 285", s.verify_gate !== "pending"),
    conn("M320 365 L320 420", s.synthesize === "done" || s.synthesize === "running"),
    conn("M320 500 L320 545", s.human_gate === "done"),
    svg("path", { d: "M440 325 C 520 300, 520 220, 440 195", stroke: "var(--rust)", "stroke-width": 2.2 }),
    svg("text", { x: 540, y: 262, "font-family": "Spline Sans Mono, monospace", "font-size": 10, fill: "var(--rust)" }, "more rings"),
  );

  const boxes = [
    ["resolve_seeds", 215, 40, 210, 50],
    ["expand_ring", 215, 150, 210, 80],
    ["verify_gate", 215, 285, 210, 80],
    ["synthesize", 215, 420, 210, 50],
    ["human_gate", 200, 545, 240, 50],
  ];
  for (const [name, x, y, w, h] of boxes) {
    const st = s[name];
    const bs = boxStyle(st);
    const [l1, l2] = lines[name][st];
    const title = name === "human_gate" ? "human gate ◇" : name;
    const tall = h === 80;
    const g = svg("g", { opacity: bs.opacity });
    g.append(svg("rect", {
      x, y, width: w, height: h, rx: 4, fill: bs.fill,
      stroke: bs.stroke, "stroke-width": bs.width,
      ...(bs.dash ? { "stroke-dasharray": bs.dash } : {}),
    }));
    g.append(svg("text", {
      x: 320, y: y + (tall ? 26 : 21), "text-anchor": "middle",
      "font-family": "Spline Sans Mono, monospace", "font-size": 12,
      fill: st === "pending" ? "var(--muted)" : "var(--ink)",
    }, title));
    const l1Color = name === "verify_gate" && st === "done" ? "var(--pass)"
      : st === "done" ? "var(--pass)" : st === "running" ? "var(--rust)" : "var(--faint)";
    if (l1) {
      g.append(svg("text", {
        x: 320, y: y + (tall ? 44 : 38), "text-anchor": "middle",
        "font-family": "Spline Sans Mono, monospace", "font-size": 9.5, fill: l1Color,
      }, l1));
    }
    if (l2) {
      const l2Color = name === "verify_gate"
        && Math.max(0, impactish ? droppedRing : dropped.length) > 0
        ? "var(--drop)" : "var(--faint)";
      g.append(svg("text", {
        x: 320, y: y + 61, "text-anchor": "middle",
        "font-family": "Spline Sans Mono, monospace", "font-size": 9.5, fill: l2Color,
      }, l2));
    }
    root.append(g);
  }

  // oracle box, attached left of verify_gate
  root.append(
    svg("g", {},
      svg("rect", { x: 30, y: 285, width: 140, height: 80, rx: 4, fill: "var(--panel)", stroke: "var(--line)", "stroke-width": 1.6 }),
      svg("text", { x: 100, y: 315, "text-anchor": "middle", "font-family": "Spline Sans Mono, monospace", "font-size": 10.5, fill: "var(--muted)" }, "oracle"),
      svg("text", { x: 100, y: 333, "text-anchor": "middle", "font-family": "Spline Sans Mono, monospace", "font-size": 9, fill: "var(--faint)" }, "edge_exists()"),
      svg("text", { x: 100, y: 348, "text-anchor": "middle", "font-family": "Spline Sans Mono, monospace", "font-size": 9, fill: "var(--faint)" }, "deterministic")),
    svg("path", { d: "M170 325 L215 325", stroke: "var(--ink)", "stroke-width": 1.8 }),
  );

  host.append(root);
}

// -- feed ---------------------------------------------------------------------

function feedLine(ts, cls, ...content) {
  return el("div", { class: `feed-line${cls ? " " + cls : ""}` },
    el("span", { class: "ts" }, ts == null ? "" : fmtClock(ts)),
    el("span", {}, ...content));
}

// Feed lines speak each workflow's own vocabulary, derived from the payload
// fields that workflow actually fills (impact: seeds/rings, atlas:
// modules/summaries, docs-drift: claims/stale). Generic when unsure.
function renderFeed(feed, d, workflow) {
  const stick = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 30;
  feed.textContent = "";
  if (d.start) {
    feed.append(feedLine(d.start.ts, null, el("b", {}, "start"), ` — workflow ${workflow}`));
  }
  const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
  let prevV = 0, prevD = 0, seenSeeds = false;
  for (const e of d.turns) {
    if (!seenSeeds && Array.isArray(e.seeds)) {
      // impact-shaped run: seeds resolved up front
      seenSeeds = true;
      const n = e.seeds.length;
      feed.append(feedLine(e.ts, null,
        el("b", {}, "resolve_seeds"), ` — ${plural(n, "seed")} resolved in the graph`));
    }
    const verified = e.verified || [];
    const dropped = e.dropped || [];
    const isAtlasTurn = verified.some((c) => c && c.module != null)
      || dropped.some((c) => c && c.module != null);
    const isDriftTurn = Array.isArray(e.stale) || e.claims != null;

    if (e.node === "verify_gate" && isAtlasTurn) {
      // atlas: module summaries pass the gate, ungrounded mentions drop
      const newV = verified.slice(prevV).map((c) => c.module).filter(Boolean);
      const newD = dropped.slice(prevD);
      const bits = [el("b", {}, "verify_gate"), " — ",
        el("span", { style: { color: "var(--pass)" } },
          `${newV.length} module ${newV.length === 1 ? "summary" : "summaries"} verified`)];
      if (newV.length > 0 && newV.length <= 3) {
        bits.push(": ", el("span", { class: "mono" }, newV.join(", ")));
      }
      bits.push(", ", el("span", { style: { color: newD.length > 0 ? "var(--drop)" : "var(--muted)" } },
        `${plural(newD.length, "claim")} dropped`));
      const first = newD[0];
      if (first) {
        bits.push(": ", el("span", { class: "mono" }, String(first.claim || first.qualname || "?")),
          ` (${first.reason || "dropped"})`);
      }
      feed.append(feedLine(e.ts, "gate", ...bits));
      prevV = verified.length; prevD = dropped.length;
    } else if (e.node === "verify_gate" && Array.isArray(e.seeds)) {
      // impact: ring expansion + the gate's pass/drop ledger
      const v = verified.length, dr = dropped.length;
      const ring = e.rings_done ?? "?";
      const passed = v - prevV, droppedN = dr - prevD;
      feed.append(feedLine(e.ts, null,
        el("b", {}, "expand_ring"), ` ring ${ring} — ${passed + droppedN} candidates from graph edges`));
      const bits = [el("b", {}, "verify_gate"), " — ",
        el("span", { style: { color: "var(--pass)" } }, `${passed} passed`), ", ",
        el("span", { style: { color: droppedN > 0 ? "var(--drop)" : "var(--muted)" } }, `${droppedN} dropped`)];
      if (droppedN > 0) {
        const first = dropped[prevD];
        if (first) {
          bits.push(": ", el("span", { class: "mono" }, first.qualname),
            ` (${first.reason || first.why || "dropped"})`);
        }
      }
      feed.append(feedLine(e.ts, "gate", ...bits));
      prevV = v; prevD = dr;
    } else if (e.node === "synthesize") {
      feed.append(feedLine(e.ts, null,
        el("b", {}, "synthesize"), e.has_draft ? " — draft ready for the human gate" : " — nothing to draft"));
    } else if (isDriftTurn) {
      // docs-drift: claims checked against the graph, stale surfaced
      const staleN = (e.stale || []).length;
      const bits = [el("b", {}, String(e.node)), " — ",
        `${plural(e.claims ?? staleN, "doc reference")} checked, `,
        el("span", { style: { color: staleN > 0 ? "var(--drop)" : "var(--pass)" } },
          `${staleN} stale`)];
      const first = (e.stale || [])[0];
      if (first) {
        bits.push(": ", el("span", { class: "mono" }, String(first.symbol)),
          ` (${first.doc}:${first.line})`);
      }
      feed.append(feedLine(e.ts, null, ...bits));
    } else if (e.node === "verify_gate") {
      // unknown workflow shape — stay generic and honest
      feed.append(feedLine(e.ts, "gate",
        el("b", {}, "verify_gate"), ` — ${plural(verified.length, "claim")} verified, `
        + `${plural(dropped.length, "claim")} dropped`));
      prevV = verified.length; prevD = dropped.length;
    } else {
      feed.append(feedLine(e.ts, null, el("b", {}, String(e.node)), " — turn"));
    }
  }
  if (d.finish) {
    const scores = d.finish.scores
      ? " · " + Object.entries(d.finish.scores).map(([k, v]) => `${k} ${fmtScore(v)}`).join(" · ")
      : "";
    feed.append(feedLine(d.finish.ts, null,
      el("b", {}, "finish"), ` — ${d.finish.outcome || "done"}`,
      el("span", { class: "dim" }, scores)));
  } else {
    const last = d.turns[d.turns.length - 1] || d.start;
    feed.append(feedLine(last?.ts, "live", "● awaiting next turn…"));
  }
  if (stick) feed.scrollTop = feed.scrollHeight;
}
