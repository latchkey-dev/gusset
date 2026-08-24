// #/ladder — autonomy per invariant + the decision ledger (ViewLadder mockup).

import { el, getJSON, emptyState, explainer, fmtScore, fmtStamp } from "../util.js";

function ladderHelp() {
  return explainer(
      "How much Gusset is allowed to do on its own \u2014 one card per job.",
      "Every job starts out only able to write a report. It earns the right to comment on a pull request, then to open one, by getting things right repeatedly. Each small bar is one run; filled means that run scored clean.",
      `It takes ${PROMOTE_RUNS} clean runs in a row to move up, and 3 bad runs out of the last 5 to drop back down. Nobody has to approve either \u2014 the score history decides.`,
      "The top level, changing files directly, is never earned this way. Only you can grant it, by editing gusset.toml by hand.",
      "Every promotion, demotion and run is recorded with its reason, and the record is committed to your repo \u2014 so the history is auditable rather than something you take on trust.",
    );
}

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
      "Gusset isn\u2019t set up on this repo yet",
      "Nothing here is broken. This page shows how much each of Gusset\u2019s jobs is trusted to do on its own, and that only exists once you install it on a repo. Run this to create gusset.toml and the GitHub Action, and the jobs will appear here.",
      "gusset init",
      ladderHelp(),
    ));
    ctx.setHeader("ladder · no jobs set up yet");
    return;
  }

  ctx.setHeader("ladder · what each job may do on its own");

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
      el("div", { class: "k" }, "HISTORY \u2014 EVERY DECISION AND WHY"),
      el("div", { class: "src" }, ".gusset/ladder.jsonl · committed to the repo")),
    body,
    el("div", { class: "ledger-rules" },
      el("span", {}, `Promotion: ${PROMOTE_RUNS} consecutive runs ≥ ${PROMOTE_THRESHOLD}`),
      el("span", {}, "·"),
      el("span", {}, `Demotion: 3 of 5 below ${DEMOTE_THRESHOLD}`),
      el("span", {}, "·"),
      el("span", {}, "\u00b7"),
      el("span", {}, el("b", {},
        "Changing files directly is never earned \u2014 only you can grant it, in gusset.toml"))));

  const explainRow = el("div", { class: "explainer-row" },
    ladderHelp());

  container.append(el("div", { class: "ladder-wrap dotbg" }, explainRow, grid, ledgerCard));
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
