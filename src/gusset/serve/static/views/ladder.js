// #/ladder — autonomy per invariant + the decision ledger (ViewLadder mockup).

import { el, getJSON, emptyState, fmtScore, fmtStamp } from "../util.js";

const LEVELS = ["report", "comment", "propose", "act"];
const PROMOTE_RUNS = 15;
const PROMOTE_THRESHOLD = 0.9;
const DEMOTE_THRESHOLD = 0.8;

export async function mountLadder(container, params, ctx) {
  let data;
  try { data = await getJSON("/api/ladder"); }
  catch { data = { invariants: [], ledger: [] }; }

  const invariants = data.invariants || [];
  const ledger = data.ledger || [];

  if (invariants.length === 0 && ledger.length === 0) {
    container.append(emptyState(
      "No ladder yet",
      "Define invariants in gusset.toml — the ladder raises their autonomy only on sustained scores, and lowers it on regression.",
      "gusset init",
    ));
    ctx.setHeader("ladder · no invariants yet");
    return;
  }

  ctx.setHeader("ladder · autonomy earned per invariant");

  // last level-change per invariant (ladder moves ±1, so prev = level ∓ 1)
  const lastLevelEvent = new Map();
  for (const e of ledger) {
    if (e.type === "level") lastLevelEvent.set(e.invariant, e);
  }

  const grid = el("div", { class: "inv-grid" });
  for (const inv of invariants) grid.append(invariantCard(inv, lastLevelEvent.get(inv.name)));

  const body = el("div", { class: "ledger-body" });
  for (const e of [...ledger].reverse()) body.append(ledgerLine(e));
  if (ledger.length === 0) {
    body.append(el("div", { class: "ledger-line" },
      el("span", { class: "detail" }, "no ledger entries yet — every run and level change lands here")));
  }

  const ledgerCard = el("div", { class: "card ledger-card" },
    el("div", { class: "ledger-head" },
      el("div", { class: "k" }, "LEDGER — EVERY DECISION, WITH ITS REASON"),
      el("div", { class: "src" }, ".gusset/ladder.jsonl · committed to the repo")),
    body,
    el("div", { class: "ledger-rules" },
      el("span", {}, `Promotion: ${PROMOTE_RUNS} consecutive runs ≥ ${PROMOTE_THRESHOLD}`),
      el("span", {}, "·"),
      el("span", {}, `Demotion: 3 of 5 below ${DEMOTE_THRESHOLD}`),
      el("span", {}, "·"),
      el("span", {}, el("b", {}, "ACT is never ladder-granted — humans only, in gusset.toml"))));

  container.append(el("div", { class: "ladder-wrap dotbg" }, grid, ledgerCard));
}

function invariantCard(inv, levelEvent) {
  const runs = inv.runs || [];
  const levelIdx = Math.max(0, LEVELS.indexOf(inv.level));
  const ceilingIdx = Math.max(0, LEVELS.indexOf(inv.ceiling));
  const demoted = !!levelEvent && String(levelEvent.reason || "").includes("demot");

  let streak = 0;
  for (let i = runs.length - 1; i >= 0; i--) {
    if ((runs[i].min_score ?? 0) >= PROMOTE_THRESHOLD) streak += 1;
    else break;
  }
  const promoting = !demoted && levelIdx < ceilingIdx && streak > 0;

  // level chip + note
  const chip = el("span", {
    class: `level-chip${demoted ? " down" : levelIdx > 0 ? " filled" : ""}`,
  }, `${demoted ? "↓ " : ""}${inv.level.toUpperCase()}`);
  let note;
  if (demoted) {
    note = el("span", { class: "inv-note drop" }, `demoted ${fmtStamp(levelEvent.ts).slice(0, 5)}`);
  } else if (promoting) {
    note = el("span", { class: "inv-note rust" },
      `${streak} clean of ${PROMOTE_RUNS} → ${LEVELS[levelIdx + 1]}`);
  } else {
    note = el("span", { class: "inv-note" }, `ceiling: ${inv.ceiling}`);
  }

  // bar strip: last runs (height = min_score), ghost bars up to the promotion target
  const strip = el("div", { class: "bar-strip" });
  const ghosts = promoting ? Math.max(0, PROMOTE_RUNS - streak) : 0;
  const shownRuns = runs.slice(-(20 - ghosts));
  for (const r of shownRuns) {
    const v = Math.max(0, Math.min(1, r.min_score ?? 0));
    strip.append(el("div", {
      class: v >= DEMOTE_THRESHOLD ? "ok" : "bad",
      style: { height: `${Math.max(8, Math.round(v * 100))}%` },
      title: `${fmtStamp(r.ts)} · min ${fmtScore(r.min_score)}`,
    }));
  }
  for (let i = 0; i < ghosts; i++) strip.append(el("div", { class: "ghost" }));
  if (runs.length === 0 && ghosts === 0) {
    for (let i = 0; i < 3; i++) strip.append(el("div", { class: "ghost" }));
  }

  // caption
  let caption;
  if (demoted) {
    caption = String(levelEvent.reason || "demoted on regression");
  } else if (promoting) {
    const left = PROMOTE_RUNS - streak;
    caption = `streak ${streak} — ${left} more clean run${left === 1 ? "" : "s"} to promotion`;
  } else if (runs.length) {
    const minAll = Math.min(...runs.map((r) => r.min_score ?? 0));
    caption = `${runs.length} run${runs.length === 1 ? "" : "s"} · min ${fmtScore(minAll)}${levelIdx >= ceilingIdx ? " · at ceiling" : ""}`;
  } else {
    caption = `no scored runs yet · trigger: ${inv.trigger || "?"}`;
  }

  return el("div", { class: `card inv-card${demoted ? " demoted" : ""}` },
    el("div", { class: "name" }, inv.name),
    el("div", { class: "chips" }, chip, note),
    strip,
    el("div", { class: "inv-caption" }, caption));
}

function ledgerLine(e) {
  const when = el("span", { class: "when" }, fmtStamp(e.ts));
  const inv = el("span", { class: "inv", title: e.invariant }, e.invariant || "—");
  let rowCls = "ledger-line", type, detail;

  if (e.type === "run") {
    type = el("span", { class: "type run" }, "run ✓");
    detail = Object.entries(e.scores || {}).map(([k, v]) => `${k} ${fmtScore(v)}`).join(" · ")
      || `min ${fmtScore(e.min_score)}`;
  } else if (e.type === "level") {
    const isDemote = String(e.reason || "").includes("demot");
    const to = LEVELS[e.level] || String(e.level);
    const from = LEVELS[e.level + (isDemote ? 1 : -1)] || "?"; // ladder moves ±1
    if (isDemote) {
      rowCls += " demote";
      type = el("span", { class: "type demote" }, "DEMOTE");
    } else {
      type = el("span", { class: "type promote" }, "PROMOTE");
    }
    detail = `${from} → ${to} · "${e.reason || ""}"`;
  } else {
    // unknown event types (e.g. harness rules) render generically, never break
    type = el("span", { class: "type other" }, String(e.type || "event"));
    detail = e.reason || e.detail
      || Object.entries(e).filter(([k]) => !["type", "invariant", "ts"].includes(k))
        .map(([k, v]) => `${k} ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
  }

  return el("div", { class: rowCls }, when, inv, type,
    el("span", { class: "detail" }, detail));
}
