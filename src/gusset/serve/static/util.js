// Shared helpers: DOM building (textContent only — API strings are never
// interpolated into markup), fetch, formatting, empty states.

export async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  const data = await r.json();
  if (data && typeof data === "object" && !Array.isArray(data) && data.error) {
    throw new Error(String(data.error));
  }
  return data;
}

export async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

// el('div', {class:'x', onclick:fn, style:{...}}, child, 'text', ...)
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  applyAttrs(node, attrs);
  append(node, children);
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else node.setAttribute(k, v);
  }
  append(node, children);
  return node;
}

function applyAttrs(node, attrs) {
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
    else if (k.startsWith("on") && typeof v === "function") {
      node.addEventListener(k.slice(2), v);
    } else if (k === "dataset") Object.assign(node.dataset, v);
    else if (typeof v === "boolean") { if (v) node.setAttribute(k, ""); }
    else node.setAttribute(k, v);
  }
}

function append(node, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
}

export function clear(node) {
  node.textContent = "";
  return node;
}

// -- formatting --------------------------------------------------------------

export function fmtClock(epoch) {
  // epoch seconds → HH:MM:SS local
  const d = new Date(epoch * 1000);
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0")).join(":");
}

export function fmtStamp(ts) {
  // ISO string or epoch → "MM-DD HH:MM"
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts ?? "");
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fmtScore(v) {
  return typeof v === "number" ? v.toFixed(2) : "—";
}

export function fmtInt(n) {
  return Number(n || 0).toLocaleString("en-US");
}

// -- shared components -------------------------------------------------------

export function codeBox(cmd) {
  const box = el("div", { class: "codebox", title: "click to copy" }, cmd);
  box.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      const prev = box.textContent;
      box.textContent = "copied ✓";
      setTimeout(() => { box.textContent = prev; }, 900);
    } catch { /* clipboard unavailable — the text is selectable */ }
  });
  return box;
}

// Small transient notice, bottom center. One at a time.
export function toast(text) {
  document.querySelector(".toast")?.remove();
  const t = el("div", { class: "toast" }, text);
  document.body.append(t);
  setTimeout(() => { t.classList.add("out"); }, 2800);
  setTimeout(() => { t.remove(); }, 3300);
  return t;
}

// "ⓘ what is this?" — collapsible per-view explainer, collapsed by default.
export function explainer(...sentences) {
  const panel = el("div", { class: "explainer-panel" },
    sentences.map((s) => el("p", {}, s)));
  panel.hidden = true;
  const btn = el("button", {
    class: "chip dim explainer-toggle", "aria-expanded": "false",
  }, "ⓘ what is this?");
  btn.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    btn.setAttribute("aria-expanded", String(!panel.hidden));
    btn.classList.toggle("dim", panel.hidden);
  });
  return el("div", { class: "explainer" }, btn, panel);
}

export function emptyState(title, sentence, cmd) {
  return el("div", { class: "empty-wrap dotbg" },
    el("div", { class: "card empty" },
      el("div", { class: "title" }, title),
      el("div", { class: "sentence" }, sentence),
      cmd ? codeBox(cmd) : null,
    ),
  );
}

// Design tokens as read from CSS — canvas rendering can't use var().
export function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const get = (name) => cs.getPropertyValue(name).trim();
  return {
    ground: get("--ground"), panel: get("--panel"), ink: get("--ink"),
    line: get("--line"), rust: get("--rust"), pass: get("--pass"),
    drop: get("--drop"), muted: get("--muted"), faint: get("--faint"),
    rustTint: get("--rust-tint"), passTint: get("--pass-tint"),
    dropTint: get("--drop-tint"), dots: get("--dots"), edge: get("--edge"),
  };
}
