// gusset serve — hash-router SPA shell.
// Routes: #/graph #/impact #/workflow #/drift #/ladder #/setup

import { el, getJSON, toast } from "./util.js";
import { mountGraph } from "./views/graph.js";
import { mountImpact } from "./views/impact.js";
import { mountWorkflow } from "./views/workflow.js";
import { mountDrift } from "./views/drift.js";
import { mountLadder } from "./views/ladder.js";
import { mountSetup } from "./views/setup.js";

const routes = {
  graph: mountGraph,
  impact: mountImpact,
  workflow: mountWorkflow,
  drift: mountDrift,
  ladder: mountLadder,
  setup: mountSetup,
};

// -- theme (persisted, default light) ----------------------------------------

const THEME_KEY = "gusset-theme";

function applyTheme(theme) {
  if (theme === "dark") document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
}

applyTheme(localStorage.getItem(THEME_KEY));

document.getElementById("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
  window.dispatchEvent(new Event("gusset-theme"));
});

// -- header ctx ---------------------------------------------------------------

const hdrMeta = document.getElementById("hdr-meta");
const hdrLive = document.getElementById("hdr-live");
const hdrLocal = document.getElementById("hdr-local");

const ctx = {
  meta: null, // /api/meta payload (may stay null if the API errors)
  repoLabel: "",
  commit: "",
  session: null, // run session the current view displays (impact/workflow set it)
  refresh: null, // view-provided hook — the heartbeat calls it on new events
  setHeader(text) { hdrMeta.textContent = text; },
  setLive(on) { hdrLive.hidden = !on; },
  remount() { navigate(); },
  syncConnected() { return syncOk; },
};

function defaultHeader() {
  return ctx.repoLabel
    ? `${ctx.repoLabel}${ctx.commit ? " @ " + ctx.commit : ""}`
    : "";
}

// -- router -------------------------------------------------------------------

const container = document.getElementById("view");
let cleanup = null;
let navSeq = 0; // stale-mount guard: heartbeat remounts can race hashchanges

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [name, query] = h.split("?");
  return { name: name || "graph", params: new URLSearchParams(query || "") };
}

async function navigate() {
  const tok = ++navSeq;
  const { name, params } = parseHash();
  const mount = routes[name] || routes.graph;

  if (typeof cleanup === "function") { try { cleanup(); } catch { /* view gone */ } }
  cleanup = null;
  ctx.refresh = null;
  ctx.session = null;
  container.textContent = "";
  container.scrollTop = 0;

  for (const tab of document.querySelectorAll("#nav .tab")) {
    tab.classList.toggle("active", tab.dataset.route === name);
  }
  ctx.setLive(false);
  ctx.setHeader(defaultHeader());
  hdrLocal.hidden = name !== "setup";
  if (name === "setup") {
    hdrLocal.textContent = `${location.host} · nothing leaves this machine`;
  }

  try {
    const done = await mount(container, params, ctx);
    if (tok !== navSeq) {
      // superseded mid-mount — tear down what this mount started
      try { if (typeof done === "function") done(); } catch { /* view gone */ }
      return;
    }
    cleanup = done;
  } catch (err) {
    if (tok !== navSeq) return;
    container.textContent = "";
    container.append(el("div", { class: "err" }, `view failed: ${err.message}`));
  }
}

window.addEventListener("hashchange", navigate);

// -- live sync (the heartbeat) ------------------------------------------------
// One EventSource for the whole app. The CLI appends run events, the server
// streams them here, and the views react immediately instead of waiting for
// a poll tick. EventSource reconnects on its own; the header badge tells the
// truth about the connection either way.

const SUPPRESS_MS = 10_000; // don't yank the page away mid-interaction
const hdrSync = document.getElementById("hdr-sync");
let syncOk = false;

let lastInteraction = 0;
for (const evName of ["pointerdown", "wheel", "keydown"]) {
  window.addEventListener(evName, () => { lastInteraction = Date.now(); },
    { capture: true, passive: true });
}

function setSync(on) {
  syncOk = on;
  hdrSync.textContent = on ? "● live" : "○ offline";
  hdrSync.classList.toggle("off", !on);
}

function routeFor(ev) {
  return ev.workflow === "impact"
    ? `#/impact?id=${encodeURIComponent(ev.session_id)}`
    : `#/workflow?id=${encodeURIComponent(ev.session_id)}`;
}

// A toast that follows the run when clicked — used when auto-navigation is
// suppressed because the user was just interacting with the page.
function followToast(text, target) {
  document.querySelector(".toast")?.remove();
  const t = el("div", { class: "toast", role: "button", style: { cursor: "pointer" } }, text);
  t.addEventListener("click", () => { t.remove(); location.hash = target; });
  document.body.append(t);
  setTimeout(() => { t.classList.add("out"); }, 7600);
  setTimeout(() => { t.remove(); }, 8100);
}

function onStart(ev) {
  if (ev.session_id === ctx.session) { ctx.refresh?.(ev); return; }
  const target = routeFor(ev);
  if (Date.now() - lastInteraction >= SUPPRESS_MS) location.hash = target;
  else followToast(`${ev.workflow || "workflow"} run started — click to follow`, target);
}

async function onIndexSignal() {
  const wasDefault = hdrMeta.textContent === defaultHeader();
  try {
    ctx.meta = await getJSON("/api/meta");
    const stats = ctx.meta.stats || {};
    const root = (stats.meta && stats.meta.root) || "";
    ctx.repoLabel = ctx.meta.repo || root.split("/").filter(Boolean).pop() || "repo";
    ctx.commit = ((stats.meta && stats.meta.commit) || "").slice(0, 7);
  } catch { return; /* server hiccup — the next signal retries */ }
  if (parseHash().name === "graph" && typeof ctx.refresh === "function") {
    ctx.refresh(); // refetches graph + re-warms the sim, camera preserved
  } else if (wasDefault) {
    ctx.setHeader(defaultHeader()); // commit text only; view headers stay
  }
}

function handleEvent(ev) {
  if (!ev || typeof ev !== "object") return;
  if (ev.session_id === "_signals") {
    if (ev.kind === "index") onIndexSignal();
    return;
  }
  if (ev.kind === "start") { onStart(ev); return; }
  if (ev.session_id && ev.session_id === ctx.session) {
    ctx.refresh?.(ev);
    if (ev.kind === "finish") toast(`${ev.session_id} — ${ev.outcome || "finished"}`);
  }
}

const events = new EventSource("/api/events");
events.addEventListener("open", () => setSync(true));
events.addEventListener("error", () => setSync(false));
events.addEventListener("message", (m) => {
  let ev = null;
  try { ev = JSON.parse(m.data); } catch { return; /* torn frame */ }
  try { handleEvent(ev); } catch { /* view mid-transition — next event lands */ }
});

// -- boot ---------------------------------------------------------------------

async function boot() {
  let runs = null;
  try {
    ctx.meta = await getJSON("/api/meta");
    const stats = ctx.meta.stats || {};
    const root = (stats.meta && stats.meta.root) || "";
    ctx.repoLabel = ctx.meta.repo || root.split("/").filter(Boolean).pop() || "repo";
    ctx.commit = ((stats.meta && stats.meta.commit) || "").slice(0, 7);
  } catch { /* graph db missing — views show their empty states */ }

  // First-run routing rule (keep it simple): land on #/graph by default;
  // land on #/setup only when the URL has no hash AND /api/runs returns []
  // (a fresh install with nothing to show yet).
  if (!location.hash) {
    try { runs = await getJSON("/api/runs"); } catch { runs = []; }
    location.hash = Array.isArray(runs) && runs.length === 0 ? "#/setup" : "#/graph";
    // hashchange fires navigate()
    return;
  }
  navigate();
}

boot();
