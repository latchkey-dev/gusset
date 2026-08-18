// #/drift — docs → symbols tether map (ViewDrift mockup).
// The API reports stale refs + a total claims count; healthy tethers are
// synthesized at doc level ("n refs · all resolve") since per-ref detail
// for healthy claims isn't shipped.

import { el, svg, getJSON, emptyState } from "../util.js";

const VB_W = 760, VB_H = 690;

const STDLIB_PREFIXES = ["asyncio.", "typing.", "json.", "os.", "pathlib."];

function explain(symbol) {
  if (!symbol.includes(".")) {
    return ["GitHub concept formatted as code — allowlist candidate.", null];
  }
  if (STDLIB_PREFIXES.some((p) => symbol.startsWith(p))) {
    return ["Resolves to no symbol in the graph. Likely an ", "external stdlib reference",
      " — candidate for the allowlist, not a docs fix."];
  }
  return ["Resolves to no symbol in the graph — an ", "external or renamed symbol",
    "; check whether the doc or the code moved."];
}

export async function mountDrift(container, params, ctx) {
  let data;
  try { data = await getJSON(`/api/drift${params.get("id") ? "?id=" + encodeURIComponent(params.get("id")) : ""}`); }
  catch { data = { session_id: null }; }

  if (!data.session_id) {
    container.append(emptyState(
      "No drift run yet",
      "Check every backticked symbol path in your docs against the graph — stale references surface here.",
      "gusset docs-drift",
    ));
    ctx.setHeader("drift · no runs yet");
    return;
  }

  const stale = data.stale || [];
  const checked = data.claims_checked ?? null;
  const resolves = checked != null ? Math.max(0, checked - stale.length) : null;

  ctx.setHeader(`drift${checked != null ? ` · ${checked} references checked` : ""} · session ${data.session_id}`);

  // group stale refs per doc
  const byDoc = new Map();
  for (const c of stale) {
    if (!byDoc.has(c.doc)) byDoc.set(c.doc, []);
    byDoc.get(c.doc).push(c);
  }
  const docs = [...byDoc.entries()].map(([doc, refs]) => ({ doc, refs, stale: true }));
  if (resolves !== null && resolves > 0) {
    docs.push({
      doc: docs.length ? "all other docs" : "all docs",
      refs: [], stale: false, healthy: resolves,
    });
  }

  // -- tether map (SVG) ------------------------------------------------------
  const svgEl = svg("svg", {
    class: "drift-svg", viewBox: `0 0 ${VB_W} ${VB_H}`,
    preserveAspectRatio: "xMidYMid meet", fill: "none",
  });

  const shown = docs.slice(0, 5);
  const step = Math.min(180, 520 / Math.max(1, shown.length - 1) || 180);
  const yTop = shown.length > 1 ? 345 - ((shown.length - 1) * step) / 2 : 320;

  let symY = 120; // running vertical slot for right-hand symbol nodes
  const paths = svg("g"), nodes = svg("g"), labels = svg("g"), boxes = svg("g");
  svgEl.append(paths, boxes, nodes, labels);

  shown.forEach((d, i) => {
    const by = yTop + i * step;
    const bx = 60, bw = 180, bh = 56;
    const cy = by + bh / 2;
    // doc box
    boxes.append(svg("rect", {
      x: bx, y: by, width: bw, height: bh, rx: 3,
      fill: d.stale ? "var(--drop-tint)" : "var(--panel)",
      stroke: d.stale ? "var(--drop)" : "var(--ink)",
      "stroke-width": d.stale ? 2 : 1.6,
    }));
    boxes.append(svg("text", {
      x: bx + bw / 2, y: by + 23, "text-anchor": "middle",
      "font-family": "Spline Sans Mono, monospace", "font-size": 10.5, fill: "var(--ink)",
    }, truncMiddle(d.doc, 26)));
    boxes.append(svg("text", {
      x: bx + bw / 2, y: by + 41, "text-anchor": "middle",
      "font-family": "Spline Sans Mono, monospace", "font-size": 9,
      fill: d.stale ? "var(--drop)" : "var(--pass)",
    }, d.stale ? `${d.refs.length} stale ref${d.refs.length === 1 ? "" : "s"}` : `${d.healthy} refs · all resolve`));

    const targets = d.stale ? d.refs.slice(0, 2) : [null];
    for (const ref of targets) {
      const ty = symY;
      symY += 78;
      const tx = 440 + ((ty / 78) % 2) * 20;
      const curve = `M${bx + bw} ${cy} C ${bx + bw + 100} ${cy}, ${tx - 120} ${ty}, ${tx - 10} ${ty}`;
      if (d.stale) {
        paths.append(svg("path", { d: curve, stroke: "var(--drop)", "stroke-width": 1.8, "stroke-dasharray": "6 5" }));
        // ghost node with X
        nodes.append(
          svg("circle", { cx: tx, cy: ty, r: 9, fill: "none", stroke: "var(--drop)", "stroke-width": 1.8, "stroke-dasharray": "3 3" }),
          svg("path", { d: `M${tx - 5} ${ty - 5} l10 10 M${tx + 5} ${ty - 5} l-10 10`, stroke: "var(--drop)", "stroke-width": 1.6 }),
        );
        labels.append(svg("text", {
          x: tx + 18, y: ty - 8, "font-family": "Spline Sans Mono, monospace",
          "font-size": 9.5, fill: "var(--drop)",
        }, `${ref.symbol} — not in graph`));
        labels.append(svg("text", {
          x: tx + 18, y: ty + 6, "font-family": "Spline Sans Mono, monospace",
          "font-size": 8.5, fill: "var(--faint)",
        }, `${shortDoc(ref.doc)}:${ref.line}`));
      } else {
        paths.append(svg("path", { d: curve, stroke: "var(--faint)", "stroke-width": 1.5 }));
        nodes.append(svg("circle", { cx: tx, cy: ty, r: 9, fill: "var(--panel)", stroke: "var(--ink)", "stroke-width": 1.6 }));
        labels.append(svg("text", {
          x: tx + 18, y: ty + 3, "font-family": "Spline Sans Mono, monospace",
          "font-size": 9.5, fill: "var(--ink)",
        }, "resolved symbols"));
      }
    }
    if (d.stale && d.refs.length > 2) {
      labels.append(svg("text", {
        x: bx + bw / 2, y: by + bh + 14, "text-anchor": "middle",
        "font-family": "Spline Sans Mono, monospace", "font-size": 8.5, fill: "var(--faint)",
      }, `+ ${d.refs.length - 2} more`));
    }
  });

  const pill = el("div", { class: "drift-pill" },
    resolves != null
      ? el("span", {}, el("span", { style: { color: "var(--pass)" } }, String(resolves)), " resolve")
      : null,
    el("span", {}, el("span", { style: { color: "var(--drop)" } }, String(stale.length)), " stale"),
    el("span", { style: { color: "var(--faint)" } }, "docs → symbols"));

  const stage = el("div", { class: "drift-stage dotbg" }, svgEl, pill);

  // -- right panel: stale reference cards ------------------------------------
  const cards = el("div", { class: "drift-cards" });
  if (stale.length === 0) {
    cards.append(el("div", { class: "footnote" },
      "Nothing stale — every doc reference resolves in the graph."));
  }
  for (const c of stale) {
    const [pre, bold, post] = explain(c.symbol);
    const why = el("div", { class: "why" }, pre);
    if (bold) why.append(el("b", {}, bold), post ?? "");
    const openBtn = el("button", {
      class: "chipbtn dim",
      title: `copy ${c.doc}:${c.line}`,
      onclick: async (ev) => {
        try {
          await navigator.clipboard.writeText(`${c.doc}:${c.line}`);
          ev.currentTarget.textContent = "copied ✓";
          setTimeout(() => { openBtn.textContent = "open doc"; }, 900);
        } catch { /* clipboard unavailable */ }
      },
    }, "open doc");
    cards.append(el("div", { class: "stale-card" },
      el("div", { class: "head" },
        el("span", { class: "sym" }, c.symbol),
        el("span", { class: "loc" }, `${shortDoc(c.doc)}:${c.line}`)),
      why,
      el("div", { class: "chips" },
        el("button", { class: "chipbtn", title: "coming with the allowlist feature" }, "allowlist"),
        openBtn)));
  }

  const right = el("div", { class: "drift-right" },
    el("div", { class: "drift-right-head" }, el("div", { class: "k" }, "STALE REFERENCES")),
    cards);

  container.append(el("div", { class: "view3" }, stage, right));
}

function truncMiddle(s, max) {
  if (s.length <= max) return s;
  const half = Math.floor((max - 1) / 2);
  return s.slice(0, half) + "…" + s.slice(-half);
}

function shortDoc(doc) {
  return doc.length > 26 ? "…" + doc.slice(-24) : doc;
}
