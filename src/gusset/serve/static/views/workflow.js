// #/workflow — live DAG + turn feed for a run (ViewWorkflow mockup).
// Note: the impact workflow only fires turn events at verify_gate and
// synthesize; resolve_seeds / expand_ring status is inferred from those.

import { el, svg, getJSON, emptyState, fmtClock, fmtScore } from "../util.js";

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
    el("div", { class: "overlay-chips" }, el("span", { class: "chip dim" }, "RUN"), picker),
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
    renderDag(dagHost, d, s);
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

function renderDag(host, d, s) {
  host.textContent = "";
  const seeds = d.lastTurn?.seeds || [];
  const ringsDone = d.lastTurn?.rings_done ?? d.gates.length;
  const verified = d.lastGate?.verified || [];
  const dropped = d.lastGate?.dropped || [];
  const prevGate = d.gates[d.gates.length - 2] || null;
  const passedRing = verified.length - (prevGate?.verified?.length || 0);
  const droppedRing = dropped.length - (prevGate?.dropped?.length || 0);
  const dur = (a, b) => (a && b && b.ts > a.ts) ? ` · ${(b.ts - a.ts).toFixed(1)}s` : "";

  const lines = {
    resolve_seeds: {
      done: [`✓ ${seeds.length} seed${seeds.length === 1 ? "" : "s"}${dur(d.start, d.turns[0])}`, null],
      running: ["● resolving seeds…", null],
      pending: ["pending", null],
    },
    expand_ring: {
      done: [`✓ ${ringsDone} ring${ringsDone === 1 ? "" : "s"} expanded`, null],
      running: [`● running · ring ${ringsDone + 1}`, `${verified.length} verified so far`],
      pending: ["pending", null],
    },
    verify_gate: {
      done: [`ring ${ringsDone}: ${Math.max(0, passedRing)} passed`, `${Math.max(0, droppedRing)} dropped (logged)`],
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
      const l2Color = name === "verify_gate" && Math.max(0, droppedRing) > 0
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

function renderFeed(feed, d, workflow) {
  const stick = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 30;
  feed.textContent = "";
  if (d.start) {
    feed.append(feedLine(d.start.ts, null, el("b", {}, "start"), ` — workflow ${workflow}`));
  }
  let prevV = 0, prevD = 0, seenSeeds = false;
  for (const e of d.turns) {
    if (!seenSeeds) {
      seenSeeds = true;
      const n = (e.seeds || []).length;
      feed.append(feedLine(e.ts, null,
        el("b", {}, "resolve_seeds"), ` — ${n} seed${n === 1 ? "" : "s"} resolved in the graph`));
    }
    if (e.node === "verify_gate") {
      const v = (e.verified || []).length, dr = (e.dropped || []).length;
      const ring = e.rings_done ?? "?";
      const passed = v - prevV, droppedN = dr - prevD;
      feed.append(feedLine(e.ts, null,
        el("b", {}, "expand_ring"), ` ring ${ring} — ${passed + droppedN} candidates from graph edges`));
      const bits = [el("b", {}, "verify_gate"), " — ",
        el("span", { style: { color: "var(--pass)" } }, `${passed} passed`), ", ",
        el("span", { style: { color: droppedN > 0 ? "var(--drop)" : "var(--muted)" } }, `${droppedN} dropped`)];
      if (droppedN > 0) {
        const first = (e.dropped || [])[prevD];
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
