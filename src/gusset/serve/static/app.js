// gusset serve — hash-router SPA shell.
// Routes: #/graph #/impact #/workflow #/drift #/ladder #/setup

import { el, getJSON } from "./util.js";
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
  setHeader(text) { hdrMeta.textContent = text; },
  setLive(on) { hdrLive.hidden = !on; },
};

function defaultHeader() {
  return ctx.repoLabel
    ? `${ctx.repoLabel}${ctx.commit ? " @ " + ctx.commit : ""}`
    : "";
}

// -- router -------------------------------------------------------------------

const container = document.getElementById("view");
let cleanup = null;

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [name, query] = h.split("?");
  return { name: name || "graph", params: new URLSearchParams(query || "") };
}

async function navigate() {
  const { name, params } = parseHash();
  const mount = routes[name] || routes.graph;

  if (typeof cleanup === "function") { try { cleanup(); } catch { /* view gone */ } }
  cleanup = null;
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
    cleanup = await mount(container, params, ctx);
  } catch (err) {
    container.textContent = "";
    container.append(el("div", { class: "err" }, `view failed: ${err.message}`));
  }
}

window.addEventListener("hashchange", navigate);

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
