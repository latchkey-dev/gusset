// #/graph — force-directed symbol graph on <canvas> (ViewGraph mockup).

import { el, getJSON, emptyState, fmtInt, tokens } from "../util.js";
import { createSim } from "../sim.js";

const GROUPS = [
  { key: "functions", label: "functions", kinds: ["function"] },
  { key: "classes", label: "classes & methods", kinds: ["class", "method"] },
  { key: "modules", label: "modules", kinds: ["module"] },
  { key: "packages", label: "packages", kinds: ["package"] },
];

const SIM_W = 1200;
const SIM_H = 900;

export async function mountGraph(container, params, ctx) {
  let graph;
  try {
    graph = await getJSON("/api/graph");
  } catch {
    container.append(emptyState(
      "No graph yet",
      "Index the repo to build the symbol graph this view explores.",
      "gusset index --repo .",
    ));
    return;
  }
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  if (nodes.length === 0) {
    container.append(emptyState(
      "No graph yet",
      "Index the repo to build the symbol graph this view explores.",
      "gusset index --repo .",
    ));
    return;
  }

  ctx.setHeader(ctx.repoLabel ? `${ctx.repoLabel} @ ${ctx.commit}` : "graph");

  // -- data ------------------------------------------------------------------
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links = edges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => ({ source: byId.get(e.source), target: byId.get(e.target), kind: e.kind }));
  const adj = new Map(); // id -> Set of neighbor ids
  for (const n of nodes) adj.set(n.id, new Set());
  for (const l of links) {
    adj.get(l.source.id).add(l.target.id);
    adj.get(l.target.id).add(l.source.id);
  }
  for (const n of nodes) n.degree = adj.get(n.id).size;

  const groupOf = (n) => GROUPS.find((g) => g.kinds.includes(n.kind))?.key ?? "functions";
  const groupCounts = {};
  for (const g of GROUPS) groupCounts[g.key] = 0;
  for (const n of nodes) groupCounts[groupOf(n)] += 1;

  // -- state -----------------------------------------------------------------
  const enabled = new Set(["functions", "classes", "modules"]); // mockup default
  let neighborhood = null; // Set of ids when "Show only this neighborhood"
  let selected = null;     // node object
  let hover = null;
  let selNeighbors = new Set();
  const view = { x: 0, y: 0, k: 1 };
  let visNodes = [];
  let visLinks = [];
  let dirty = true;
  let colors = tokens();

  const isVisible = (n) =>
    enabled.has(groupOf(n)) && (!neighborhood || neighborhood.has(n.id));

  function recomputeVisible(reheat = true) {
    visNodes = nodes.filter(isVisible);
    const vis = new Set(visNodes.map((n) => n.id));
    visLinks = links.filter((l) => vis.has(l.source.id) && vis.has(l.target.id));
    sim = createSim(visNodes, visLinks, { width: SIM_W, height: SIM_H });
    if (reheat) sim.reheat(0.6); else sim.stop();
    dirty = true;
  }

  let sim = createSim(nodes.filter(isVisible), [], { width: SIM_W, height: SIM_H });
  recomputeVisible(true);

  // -- left panel ------------------------------------------------------------
  const searchInput = el("input", {
    type: "text", placeholder: "search symbols…", spellcheck: "false",
  });
  const searchResults = el("div", { class: "search-results", hidden: true });
  const searchBox = el("div", { class: "searchbox" },
    svgSearchIcon(), searchInput, searchResults);

  searchInput.addEventListener("input", () => {
    const q = searchInput.value.trim().toLowerCase();
    searchResults.textContent = "";
    if (q.length < 2) { searchResults.hidden = true; return; }
    const hits = nodes
      .filter((n) => n.qualname.toLowerCase().includes(q))
      .slice(0, 8);
    if (hits.length === 0) { searchResults.hidden = true; return; }
    for (const n of hits) {
      searchResults.append(el("button", {
        onclick: () => {
          searchResults.hidden = true;
          searchInput.value = n.qualname;
          selectNode(n, true);
        },
      }, n.qualname));
    }
    searchResults.hidden = false;
  });
  searchInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") searchResults.querySelector("button")?.click();
    if (ev.key === "Escape") searchResults.hidden = true;
  });

  const filterRows = GROUPS.map((g) => {
    const input = el("input", { type: "checkbox" });
    input.checked = enabled.has(g.key);
    input.addEventListener("change", () => {
      if (input.checked) enabled.add(g.key); else enabled.delete(g.key);
      recomputeVisible(true);
    });
    return el("label", { class: "filter-row" },
      input, el("span", { class: "cbox" }), g.label,
      el("span", { class: "filter-count" }, String(groupCounts[g.key])));
  });

  const stats = ctx.meta?.stats || {};
  const totalSymbols = Object.values(stats.symbols || {}).reduce((a, b) => a + b, 0);
  const totalEdges = Object.values(stats.edges || {}).reduce((a, b) => a + b, 0);
  const unresolved = Number(stats.meta?.unresolved_refs || 0);

  const left = el("div", { class: "side left" },
    searchBox,
    el("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } },
      el("div", { class: "k" }, "SHOW"), filterRows),
    el("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } },
      el("div", { class: "k" }, "LEGEND"),
      legendRow(dotSwatch({ border: "2px solid var(--ink)", background: "var(--panel)" }), "symbol"),
      legendRow(dotSwatch({ background: "var(--rust)" }), "selected"),
      legendRow(dotSwatch({ border: "2px dashed var(--faint)" }), "package (external)"),
      legendRow(el("span", { style: { width: "16px", height: "0", borderTop: "2px solid var(--rust)" } }), "edge of selection"),
    ),
    el("div", { class: "side-foot" },
      `${fmtInt(totalSymbols)} symbols · ${fmtInt(totalEdges)} edges`,
      el("br"),
      `${fmtInt(unresolved)} unresolved (counted,`, el("br"), "never guessed)"),
  );

  // -- stage -----------------------------------------------------------------
  const canvas = el("canvas", { id: "graph-canvas" });
  const zoomChip = el("span", { class: "chip dim" }, "100%");
  const fitChip = el("button", { class: "chip", onclick: () => { fit(); } }, "fit");
  const stage = el("div", { class: "stage dotbg" },
    canvas, el("div", { class: "overlay-chips" }, fitChip, zoomChip));

  // -- right panel -----------------------------------------------------------
  const selQual = el("div", { class: "sel-qual" });
  const selSub = el("div", { class: "sel-sub" });
  const depCountEl = el("div", { class: "n" }, "–");
  const depsCountEl = el("div", { class: "n" }, "–");
  const depsList = el("div", { class: "deps-list" });
  const neighborhoodBtn = el("button", { class: "btn", onclick: toggleNeighborhood },
    "Show only this neighborhood");
  const right = el("div", { class: "side right", style: { width: "300px", display: "none" } },
    el("div", { style: { display: "flex", flexDirection: "column", gap: "3px" } },
      el("div", { class: "k" }, "SELECTED"), selQual, selSub),
    el("div", { class: "statbox2" },
      el("div", { class: "statbox hard" }, depCountEl, el("div", { class: "l" }, "DEPENDENTS")),
      el("div", { class: "statbox" }, depsCountEl, el("div", { class: "l" }, "DEPENDENCIES"))),
    el("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } },
      el("div", { class: "k" }, "DIRECT DEPENDENTS"), depsList),
    el("div", { style: { marginTop: "auto", display: "flex", flexDirection: "column", gap: "8px" } },
      el("button", {
        class: "btn primary",
        onclick: () => { if (selected) location.hash = `#/impact?seed=${encodeURIComponent(selected.qualname)}`; },
      }, "Run impact from here →"),
      neighborhoodBtn),
  );

  container.append(el("div", { class: "view3" }, left, stage, right));

  // -- selection -------------------------------------------------------------
  async function selectNode(n, center = false) {
    selected = n;
    selNeighbors = new Set(adj.get(n.id));
    right.style.display = "flex";
    selQual.textContent = n.qualname;
    selSub.textContent = `${n.kind} · ${n.path}`;
    depCountEl.textContent = "–";
    depsCountEl.textContent = "–";
    depsList.textContent = "";
    dirty = true;
    if (center) centerOn(n);
    try {
      const sym = await getJSON(`/api/symbol?q=${encodeURIComponent(n.qualname)}`);
      if (selected !== n) return; // stale response
      selSub.textContent = `${sym.kind} · ${sym.path}:${sym.line}`;
      depCountEl.textContent = String(sym.dependents.length);
      depsCountEl.textContent = String(sym.dependencies.length);
      renderDeps(sym.dependents);
    } catch {
      // fall back to local adjacency counts
      const inbound = links.filter((l) => l.target.id === n.id).map((l) => l.source.qualname);
      const outbound = links.filter((l) => l.source.id === n.id).length;
      depCountEl.textContent = String(inbound.length);
      depsCountEl.textContent = String(outbound);
      renderDeps(inbound);
    }
  }

  function renderDeps(list) {
    depsList.textContent = "";
    for (const q of list.slice(0, 6)) depsList.append(q, el("br"));
    if (list.length > 6) {
      depsList.append(el("span", { class: "deps-more" }, `+ ${list.length - 6} more`));
    }
  }

  function deselect() {
    selected = null;
    selNeighbors = new Set();
    right.style.display = "none";
    if (neighborhood) { neighborhood = null; neighborhoodBtn.textContent = "Show only this neighborhood"; recomputeVisible(true); }
    dirty = true;
  }

  function toggleNeighborhood() {
    if (!selected) return;
    if (neighborhood) {
      neighborhood = null;
      neighborhoodBtn.textContent = "Show only this neighborhood";
    } else {
      // 2-hop closure around the selection
      const set = new Set([selected.id]);
      for (const a of adj.get(selected.id)) set.add(a);
      for (const a of [...set]) for (const b of adj.get(a)) set.add(b);
      neighborhood = set;
      neighborhoodBtn.textContent = "Show full graph";
    }
    recomputeVisible(true);
    setTimeout(fit, 350); // let the sim settle a little, then frame it
  }

  // -- canvas rendering ------------------------------------------------------
  const ctx2d = canvas.getContext("2d");
  let cw = 0, ch = 0;

  function resize() {
    const r = stage.getBoundingClientRect();
    cw = Math.max(1, r.width);
    ch = Math.max(1, r.height);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(cw * dpr);
    canvas.height = Math.round(ch * dpr);
    ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
    dirty = true;
  }

  function fit() {
    if (visNodes.length === 0) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of visNodes) {
      x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y);
      x1 = Math.max(x1, n.x); y1 = Math.max(y1, n.y);
    }
    const pad = 60;
    const k = Math.min(2.5, Math.min(cw / (x1 - x0 + pad * 2 || 1), ch / (y1 - y0 + pad * 2 || 1)));
    view.k = k;
    view.x = cw / 2 - k * (x0 + x1) / 2;
    view.y = ch / 2 - k * (y0 + y1) / 2;
    zoomChip.textContent = `${Math.round(k * 100)}%`;
    dirty = true;
  }

  function centerOn(n) {
    view.x = cw / 2 - view.k * n.x;
    view.y = ch / 2 - view.k * n.y;
    dirty = true;
  }

  const radius = (n) => Math.max(4, Math.min(16, 4 + Math.sqrt(n.degree || 0) * 2.2));

  function draw() {
    ctx2d.clearRect(0, 0, cw, ch);
    ctx2d.save();
    ctx2d.translate(view.x, view.y);
    ctx2d.scale(view.k, view.k);

    const selId = selected?.id;
    // idle edges
    ctx2d.strokeStyle = colors.edge;
    ctx2d.lineWidth = 1.3 / view.k;
    ctx2d.beginPath();
    for (const l of visLinks) {
      if (selId != null && (l.source.id === selId || l.target.id === selId)) continue;
      ctx2d.moveTo(l.source.x, l.source.y);
      ctx2d.lineTo(l.target.x, l.target.y);
    }
    ctx2d.stroke();
    // edges of selection
    if (selId != null) {
      ctx2d.strokeStyle = colors.rust;
      ctx2d.lineWidth = 2.2 / view.k;
      ctx2d.beginPath();
      for (const l of visLinks) {
        if (l.source.id !== selId && l.target.id !== selId) continue;
        ctx2d.moveTo(l.source.x, l.source.y);
        ctx2d.lineTo(l.target.x, l.target.y);
      }
      ctx2d.stroke();
    }

    // nodes
    for (const n of visNodes) {
      const r = radius(n);
      const isSel = n.id === selId;
      const isNb = selNeighbors.has(n.id);
      const isPkg = n.kind === "package";
      ctx2d.beginPath();
      ctx2d.arc(n.x, n.y, isSel ? r + 3 : r, 0, Math.PI * 2);
      if (isPkg) {
        ctx2d.setLineDash([3, 3]);
        ctx2d.strokeStyle = colors.faint;
        ctx2d.lineWidth = 1.5 / view.k;
        ctx2d.stroke();
        ctx2d.setLineDash([]);
        continue;
      }
      ctx2d.fillStyle = isSel ? colors.rustTint : colors.panel;
      ctx2d.fill();
      ctx2d.strokeStyle = isSel || isNb ? colors.rust : (n.degree >= 3 ? colors.ink : colors.faint);
      ctx2d.lineWidth = (isSel ? 2.6 : isNb ? 1.9 : n.degree >= 3 ? 1.7 : 1.4) / Math.sqrt(view.k);
      ctx2d.stroke();
    }
    ctx2d.restore();

    // labels in screen space (crisp at any zoom)
    ctx2d.textAlign = "center";
    const label = (n, font, color, dy) => {
      const sx = view.x + view.k * n.x;
      const sy = view.y + view.k * n.y;
      if (sx < -80 || sx > cw + 80 || sy < -40 || sy > ch + 40) return;
      ctx2d.font = font;
      ctx2d.fillStyle = color;
      ctx2d.fillText(shortName(n.qualname), sx, sy + dy);
    };
    if (selected && isVisible(selected)) {
      const shown = [...selNeighbors].map((id) => byId.get(id)).filter(isVisible)
        .sort((a, b) => b.degree - a.degree).slice(0, 12);
      for (const n of shown) {
        label(n, '9.5px "Spline Sans Mono", monospace', colors.muted, radius(n) * view.k + 13);
      }
      ctx2d.font = '500 11px "Spline Sans Mono", monospace';
      ctx2d.fillStyle = colors.rust;
      ctx2d.fillText(shortName(selected.qualname),
        view.x + view.k * selected.x,
        view.y + view.k * selected.y + (radius(selected) + 3) * view.k + 15);
    }
    if (hover && hover !== selected && !selNeighbors.has(hover.id)) {
      label(hover, '10px "Spline Sans Mono", monospace', colors.ink, radius(hover) * view.k + 13);
    }
  }

  // -- interaction -----------------------------------------------------------
  let panning = false, moved = false, px = 0, py = 0;

  canvas.addEventListener("mousedown", (ev) => {
    panning = true; moved = false;
    px = ev.clientX; py = ev.clientY;
    canvas.classList.add("panning");
  });
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);

  function onMove(ev) {
    if (panning) {
      const dx = ev.clientX - px, dy = ev.clientY - py;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      view.x += dx; view.y += dy;
      px = ev.clientX; py = ev.clientY;
      dirty = true;
      return;
    }
    const r = canvas.getBoundingClientRect();
    const found = hitTest(ev.clientX - r.left, ev.clientY - r.top);
    if (found !== hover) { hover = found; canvas.style.cursor = found ? "pointer" : "grab"; dirty = true; }
  }

  function onUp(ev) {
    if (!panning) return;
    panning = false;
    canvas.classList.remove("panning");
    if (!moved && ev.target === canvas) {
      const r = canvas.getBoundingClientRect();
      const found = hitTest(ev.clientX - r.left, ev.clientY - r.top);
      if (found) selectNode(found);
      else deselect();
    }
  }

  function hitTest(sx, sy) {
    const wx = (sx - view.x) / view.k;
    const wy = (sy - view.y) / view.k;
    let best = null, bestD = Infinity;
    for (const n of visNodes) {
      const dx = n.x - wx, dy = n.y - wy;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < bestD) { bestD = d; best = n; }
    }
    return best && bestD <= radius(best) / 1 + 8 / view.k ? best : null;
  }

  canvas.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const r = canvas.getBoundingClientRect();
    const sx = ev.clientX - r.left, sy = ev.clientY - r.top;
    const factor = Math.exp(-ev.deltaY * 0.0016);
    const k = Math.max(0.12, Math.min(6, view.k * factor));
    // zoom about the cursor (transform, not re-sim)
    view.x = sx - (k / view.k) * (sx - view.x);
    view.y = sy - (k / view.k) * (sy - view.y);
    view.k = k;
    zoomChip.textContent = `${Math.round(k * 100)}%`;
    dirty = true;
  }, { passive: false });

  // -- loop ------------------------------------------------------------------
  let raf = 0;
  let fitted = false;
  function frame() {
    if (sim.alpha() > 0.02) { sim.tick(); dirty = true; }
    else if (!fitted) { fitted = true; fit(); }
    if (dirty) { dirty = false; draw(); }
    raf = requestAnimationFrame(frame);
  }

  const ro = new ResizeObserver(() => resize());
  ro.observe(stage);
  resize();
  // warm the layout so the first paint is already framed, then animate on
  for (let i = 0; i < 60; i++) sim.tick();
  fit();
  const onTheme = () => { colors = tokens(); dirty = true; };
  window.addEventListener("gusset-theme", onTheme);
  document.fonts?.ready?.then(() => { dirty = true; });
  raf = requestAnimationFrame(frame);

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect();
    window.removeEventListener("gusset-theme", onTheme);
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };
}

// -- little bits --------------------------------------------------------------

function shortName(qualname) {
  const parts = qualname.split(".");
  return parts.length <= 3 ? qualname : parts.slice(-3).join(".");
}

function legendRow(swatch, text) {
  return el("div", { class: "legend-row" }, swatch, text);
}

function dotSwatch(style) {
  return el("span", { style: { width: "11px", height: "11px", borderRadius: "50%", flex: "none", ...style } });
}

function svgSearchIcon() {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("width", "13"); s.setAttribute("height", "13");
  s.setAttribute("viewBox", "0 0 20 20"); s.setAttribute("fill", "none");
  s.innerHTML = '<circle cx="8" cy="8" r="5" stroke="currentColor" stroke-width="1.6"/><path d="M12 12 L17 17" stroke="currentColor" stroke-width="1.6"/>';
  s.style.color = "var(--muted)";
  s.style.flex = "none";
  return s;
}
