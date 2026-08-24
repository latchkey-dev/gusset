// #/drift — docs → symbols tether map (ViewDrift mockup).
// The API reports stale refs + a total claims count; healthy tethers are
// synthesized at doc level ("n refs · all resolve") since per-ref detail
// for healthy claims isn't shipped.

import { el, svg, getJSON, postJSON, emptyState, explainer, toast } from "../util.js";

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
  // Never derive this as checked - stale: that counts every reference we
  // deliberately did NOT check as a verified one. The backend reports the
  // three buckets separately for exactly this reason.
  const resolves = data.valid_count ?? null;
  const unanchored = data.unanchored_count ?? 0;

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

  let staleLeft = stale.length;
  const staleNum = el("span", { style: { color: "var(--drop)" } }, String(staleLeft));
  const pill = el("div", { class: "drift-pill" },
    resolves != null
      ? el("span", {}, el("span", { style: { color: "var(--pass)" } }, String(resolves)), " resolve")
      : null,
    el("span", {}, staleNum, " stale"),
    unanchored
      ? el("span", { title: "No prefix of these resolves in the graph, so they "
                          + "are prose about something else — a database column, "
                          + "an instance type, another tool's config. Reporting "
                          + "them as drift would be a guess." },
          el("span", { style: { color: "var(--faint)" } }, String(unanchored)),
          " not about this code")
      : null,
    el("span", { style: { color: "var(--faint)" } }, "docs → symbols"));

  const stage = el("div", { class: "drift-stage dotbg" }, svgEl,
    el("div", { class: "overlay-chips" }, pill,
      explainer(
        "Every backticked doc reference, checked against the graph — stale means no symbol resolves to it.",
        "Allowlist external names (stdlib, GitHub concepts) so they stop reporting; that's a judgment call, so it's a button, not a default.",
        "Exit code 2 on stale makes this a CI check.",
      )));

  // -- right panel: stale reference cards ------------------------------------
  const cards = el("div", { class: "drift-cards" });
  const nothingStale = () => el("div", { class: "footnote" },
    "Nothing stale — every doc reference resolves in the graph.");
  if (stale.length === 0) cards.append(nothingStale());
  for (const c of stale) {
    const [pre, bold, post] = explain(c.symbol);
    const why = el("div", { class: "why" }, pre);
    if (bold) why.append(el("b", {}, bold), post ?? "");

    const card = el("div", { class: "stale-card" });
    const errLine = el("div", { class: "inline-err" });
    errLine.hidden = true;
    const showErr = (msg) => { errLine.textContent = msg; errLine.hidden = false; };

    // allowlist → POST /api/allowlist, animate the card out on success
    const allowBtn = el("button", {
      class: "chipbtn",
      title: `skip ${c.symbol} in future drift runs`,
      onclick: async () => {
        errLine.hidden = true;
        allowBtn.disabled = true;
        try {
          const res = await postJSON("/api/allowlist", { symbol: c.symbol });
          if (res && res.error) { showErr(res.error); allowBtn.disabled = false; return; }
          staleLeft = Math.max(0, staleLeft - 1);
          staleNum.textContent = String(staleLeft);
          toast("added to .gusset/drift-allowlist.txt — next drift run will skip it");
          card.classList.add("leaving");
          setTimeout(() => {
            card.remove();
            if (staleLeft === 0 && !cards.querySelector(".stale-card")) cards.append(nothingStale());
          }, 280);
        } catch (err) {
          showErr(err.message || "allowlist request failed");
          allowBtn.disabled = false;
        }
      },
    }, "allowlist");

    // open doc → inline excerpt via GET /api/doc, toggles on second click
    const excerptHost = el("div");
    let excerptOpen = false;
    let excerptEl = null;
    const openBtn = el("button", {
      class: "chipbtn dim",
      title: `show ${c.doc}:${c.line}`,
      onclick: async () => {
        errLine.hidden = true;
        if (excerptOpen) {
          excerptOpen = false;
          if (excerptEl) excerptEl.hidden = true;
          openBtn.textContent = "open doc";
          return;
        }
        if (!excerptEl) {
          openBtn.textContent = "loading…";
          try {
            excerptEl = await docExcerpt(c);
          } catch (err) {
            openBtn.textContent = "open doc";
            showErr(err.message || "doc not readable");
            return;
          }
          excerptHost.append(excerptEl);
        }
        excerptEl.hidden = false;
        excerptOpen = true;
        openBtn.textContent = "close doc";
      },
    }, "open doc");

    card.append(
      el("div", { class: "head" },
        el("span", { class: "sym" }, c.symbol),
        el("span", { class: "loc" }, `${shortDoc(c.doc)}:${c.line}`)),
      why,
      el("div", { class: "chips" }, allowBtn, openBtn),
      errLine,
      excerptHost);
    cards.append(card);
  }

  const right = el("div", { class: "drift-right" },
    el("div", { class: "drift-right-head" }, el("div", { class: "k" }, "STALE REFERENCES")),
    cards);

  container.append(el("div", { class: "view3" }, stage, right));
}

// Fetch the excerpt and render it: mono, numbered from payload.start, the
// stale line highlighted. Drift runs record doc paths relative to the run's
// --repo root (often docs/), while /api/doc resolves from the repo root —
// try the likely candidate first and remember which prefix worked.
let docPrefix = null; // "" or "docs/", learned from the first successful fetch
async function docExcerpt(c) {
  const candidates = docPrefix != null
    ? [docPrefix]
    : (c.doc.startsWith("docs/") ? ["", "docs/"] : ["docs/", ""]);
  let payload = null, lastErr = null;
  for (const prefix of candidates) {
    try {
      payload = await getJSON(`/api/doc?doc=${encodeURIComponent(prefix + c.doc)}&line=${c.line}`);
      docPrefix = prefix;
      break;
    } catch (err) { lastErr = err; }
  }
  if (!payload) throw lastErr || new Error("doc not readable");
  const box = el("div", { class: "doc-excerpt" });
  (payload.lines || []).forEach((text, i) => {
    const n = (payload.start ?? 1) + i;
    box.append(el("div", { class: n === c.line ? "row hot" : "row" },
      el("span", { class: "ln" }, String(n)),
      el("span", { class: "tx" }, text || " ")));
  });
  return box;
}

function truncMiddle(s, max) {
  if (s.length <= max) return s;
  const half = Math.floor((max - 1) / 2);
  return s.slice(0, half) + "…" + s.slice(-half);
}

function shortDoc(doc) {
  return doc.length > 26 ? "…" + doc.slice(-24) : doc;
}
