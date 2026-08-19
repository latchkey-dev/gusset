// #/graph — force-directed symbol graph on <canvas> (ViewGraph mockup).

import { el, getJSON, emptyState, explainer, fmtInt, tokens } from "../util.js";
import { createSim } from "../sim.js";

const GROUPS = [
  { key: "functions", label: "functions", kinds: ["function"] },
  { key: "classes", label: "classes & methods", kinds: ["class", "method"] },
  { key: "modules", label: "modules", kinds: ["module"] },
  { key: "packages", label: "packages", kinds: ["package"] },
];

const SIM_W = 1200;
const SIM_H = 900;

// Heartbeat refresh state: an index signal remounts this view with fresh
// data while the camera, filters, and selection carry over. Old positions
// seed the new sim so the re-warm settles near the old layout instead of
// starting from scratch.
let resumeState = null;

export async function mountGraph(container, params, ctx) {
  const resume = resumeState;
  resumeState = null;
  let graph;
  try {
    graph = await getJSON("/api/graph");
  } catch {
    ctx.refresh = () => ctx.remount(); // an index signal can fill this in live
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
    ctx.refresh = () => ctx.remount(); // an index signal can fill this in live
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

  const radius = (n) => Math.max(4, Math.min(16, 4 + Math.sqrt(n.degree || 0) * 2.2));
  for (const n of nodes) n.r = radius(n); // collision radius for the sim

  if (resume) {
    // continue the previous layout: seeded nodes skip the sim's fresh start
    for (const n of nodes) {
      const p = resume.positions.get(n.qualname);
      if (p) { n.x = p.x; n.y = p.y; }
    }
  }

  // Largest connected component — the default render on big graphs, so the
  // fitted view stays airy instead of a hairball of tiny fragments.
  const componentOf = new Map(); // id -> component index
  {
    let comp = 0;
    for (const n of nodes) {
      if (componentOf.has(n.id)) continue;
      const stack = [n.id];
      componentOf.set(n.id, comp);
      while (stack.length) {
        const id = stack.pop();
        for (const nb of adj.get(id)) {
          if (!componentOf.has(nb)) { componentOf.set(nb, comp); stack.push(nb); }
        }
      }
      comp += 1;
    }
  }
  const compSizes = new Map();
  for (const c of componentOf.values()) compSizes.set(c, (compSizes.get(c) || 0) + 1);
  const mainComp = [...compSizes.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? 0;
  const mainSet = new Set(nodes.filter((n) => componentOf.get(n.id) === mainComp).map((n) => n.id));

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
  // default-focus the main component when the full graph would be a hairball
  let capped = nodes.length > 400 && mainSet.size < nodes.length;
  let seedLayout = false; // resume: first sim build continues the saved layout
  if (resume) {
    enabled.clear();
    for (const k of resume.enabled) enabled.add(k);
    if (nodes.length > 400 && mainSet.size < nodes.length) capped = resume.capped;
    seedLayout = true;
  }

  const isVisible = (n) =>
    enabled.has(groupOf(n))
    && (!capped || mainSet.has(n.id))
    && (!neighborhood || neighborhood.has(n.id));

  function recomputeVisible(reheat = true) {
    visNodes = nodes.filter(isVisible);
    const vis = new Set(visNodes.map((n) => n.id));
    visLinks = links.filter((l) => vis.has(l.source.id) && vis.has(l.target.id));
    sim = createSim(visNodes, visLinks,
      { width: SIM_W, height: SIM_H, noWarmStart: seedLayout });
    if (reheat) sim.reheat(0.6); else sim.stop();
    updateShownFoot();
    updateCapChip();
    dirty = true;
  }

  let sim = createSim(nodes.filter(isVisible), [], { width: SIM_W, height: SIM_H });

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
  const unresolved = Number(stats.meta?.unresolved_refs || 0);

  // honest footer: what's on screen vs what the graph holds
  const shownFoot = el("span");
  function updateShownFoot() {
    shownFoot.textContent =
      `${fmtInt(visNodes.length)} of ${fmtInt(nodes.length)} symbols shown · `
      + `${fmtInt(visLinks.length)} of ${fmtInt(links.length)} edges`;
  }

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
      shownFoot,
      el("br"),
      `${fmtInt(unresolved)} unresolved (counted,`, el("br"), "never guessed)"),
  );

  // -- stage -----------------------------------------------------------------
  const canvas = el("canvas", { id: "graph-canvas" });
  const zoomChip = el("span", { class: "chip dim" }, "100%");
  const fitChip = el("button", { class: "chip", onclick: () => { fit(); } }, "fit");
  const capChip = el("button", {
    class: "chip",
    onclick: () => { capped = !capped; recomputeVisible(true); setTimeout(fit, 350); },
  });
  function updateCapChip() {
    capChip.hidden = !(nodes.length > 400 && mainSet.size < nodes.length) || !!neighborhood;
    capChip.textContent = capped
      ? `show all ${fmtInt(nodes.length)}`
      : "main component only";
  }
  const stage = el("div", { class: "stage dotbg" },
    canvas,
    el("div", { class: "overlay-chips" },
      fitChip, zoomChip, capChip,
      explainer(
        "Your repo as Gusset sees it: every symbol, and only the edges it could prove — packages ring the code.",
        "This graph is the ground truth every other view checks against.",
        "Click a node to explore its dependents, then run impact from it.",
      )));

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
  recomputeVisible(true);
  seedLayout = false; // later recomputes (filter toggles) warm-start as usual

  // heartbeat hook: an index signal refetches the graph and re-warms the
  // sim; camera, filters, and selection survive the remount.
  ctx.refresh = () => {
    resumeState = {
      view: { ...view },
      selectedQual: selected?.qualname ?? null,
      enabled: [...enabled],
      capped,
      positions: new Map(nodes.filter((n) => n.x != null)
        .map((n) => [n.qualname, { x: n.x, y: n.y }])),
    };
    ctx.remount();
  };

  // -- selection -------------------------------------------------------------
  async function selectNode(n, center = false) {
    // a search hit may live outside the current subset — reveal it
    let reveal = false;
    if (capped && !mainSet.has(n.id)) { capped = false; reveal = true; }
    if (!enabled.has(groupOf(n))) {
      enabled.add(groupOf(n));
      const idx = GROUPS.findIndex((g) => g.key === groupOf(n));
      const input = filterRows[idx]?.querySelector("input");
      if (input) input.checked = true;
      reveal = true;
    }
    if (reveal) recomputeVisible(true);
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

  function draw() {
    ctx2d.clearRect(0, 0, cw, ch);
    ctx2d.save();
    ctx2d.translate(view.x, view.y);
    ctx2d.scale(view.k, view.k);

    const selId = selected?.id;
    // idle edges — thin and translucent so the structure reads airy
    ctx2d.strokeStyle = colors.edge;
    ctx2d.lineWidth = 1 / view.k;
    ctx2d.globalAlpha = 0.55;
    ctx2d.beginPath();
    for (const l of visLinks) {
      if (selId != null && (l.source.id === selId || l.target.id === selId)) continue;
      ctx2d.moveTo(l.source.x, l.source.y);
      ctx2d.lineTo(l.target.x, l.target.y);
    }
    ctx2d.stroke();
    ctx2d.globalAlpha = 1;
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

    // labels in screen space (crisp at any zoom) — only highlighted nodes
    // ever get one, each on a panel pill so it never tangles with edges,
    // greedily nudged down so pills never cover each other either.
    const specs = [];
    const mkSpec = (n, { font, color, stroke, extra }) => {
      const sx = view.x + view.k * n.x;
      const sy = view.y + view.k * n.y;
      if (sx < -160 || sx > cw + 160 || sy < -60 || sy > ch + 60) return;
      const text = shortName(n.qualname);
      ctx2d.font = font;
      const w = ctx2d.measureText(text).width + 12;
      const h = 18;
      const box = { x: sx - w / 2, y: sy + radius(n) * view.k + 7, w, h };
      for (let i = 0; i < 40; i++) {
        const hit = specs.find((s) =>
          box.x < s.box.x + s.box.w + 2 && s.box.x < box.x + box.w + 2
          && box.y < s.box.y + s.box.h + 2 && s.box.y < box.y + box.h + 2);
        if (!hit) break;
        box.y = hit.box.y + hit.box.h + 3;
      }
      specs.push({ box, text, font, color, stroke, extra });
    };
    const drawPill = ({ box, text, font, color, stroke, extra }) => {
      ctx2d.beginPath();
      if (ctx2d.roundRect) ctx2d.roundRect(box.x, box.y, box.w, box.h, 4);
      else ctx2d.rect(box.x, box.y, box.w, box.h);
      ctx2d.fillStyle = colors.panel;
      ctx2d.fill();
      ctx2d.strokeStyle = stroke;
      ctx2d.lineWidth = 1;
      ctx2d.stroke();
      ctx2d.fillStyle = color;
      ctx2d.textAlign = "center";
      ctx2d.textBaseline = "middle";
      ctx2d.font = font;
      const cxp = box.x + box.w / 2;
      ctx2d.fillText(text, cxp, box.y + box.h / 2 + 0.5);
      if (extra) {
        ctx2d.font = '10px "Spline Sans Mono", monospace';
        ctx2d.fillStyle = colors.muted;
        ctx2d.fillText(extra, cxp, box.y + box.h + 11);
      }
      ctx2d.textBaseline = "alphabetic";
    };
    if (selected && isVisible(selected)) {
      // cap: selected + its highest-degree neighbors, 12 labels total
      const nbs = [...selNeighbors].map((id) => byId.get(id)).filter(isVisible)
        .sort((a, b) => b.degree - a.degree);
      const shown = nbs.slice(0, 11);
      // selected claims its spot first, neighbors nudge around it
      mkSpec(selected, {
        font: '500 11px "Spline Sans Mono", monospace',
        color: colors.rust, stroke: colors.rust,
        extra: nbs.length > shown.length ? `+${nbs.length - shown.length} more` : null,
      });
      for (const n of shown) {
        mkSpec(n, { font: '11px "Spline Sans Mono", monospace', color: colors.ink, stroke: colors.line });
      }
      for (const s of specs.slice(1)) drawPill(s);
      if (specs.length) drawPill(specs[0]); // selected on top
    }
    if (hover && hover !== selected && !selNeighbors.has(hover.id)) {
      mkSpec(hover, { font: '11px "Spline Sans Mono", monospace', color: colors.ink, stroke: colors.ink });
      const s = specs[specs.length - 1];
      if (s) drawPill(s);
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
  for (let i = 0; i < 180; i++) sim.tick();
  if (resume) {
    Object.assign(view, resume.view); // keep the saved camera — no auto-fit
    zoomChip.textContent = `${Math.round(view.k * 100)}%`;
    fitted = true;
    const keep = resume.selectedQual
      && nodes.find((n) => n.qualname === resume.selectedQual);
    if (keep) selectNode(keep);
    dirty = true;
  } else {
    fit();
  }
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
