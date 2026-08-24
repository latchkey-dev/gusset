// #/setup — key validation + .env writing (ViewSetup mockup).
// Keys are POSTed to the local server only; it validates them live and,
// on "Save & index repo", writes .env in the repo. Nothing leaves the machine.

import { el, explainer, postJSON } from "../util.js";

export async function mountSetup(container, params, ctx) {
  ctx.setHeader("first run · setup");

  const fields = {}; // name -> {input, status, extra?}

  function statusEl() {
    return el("div", { class: "val-status", style: { display: "none" } });
  }

  function setStatus(name, kind, text) {
    const st = fields[name].status;
    st.className = "val-status" + (kind ? ` ${kind}` : "");
    st.style.display = text ? "flex" : "none";
    st.textContent = text || "";
    const input = fields[name].input;
    input.classList.toggle("ok", kind === "ok");
    input.classList.toggle("bad", kind === "bad");
  }

  function collectKeys() {
    const keys = {};
    if (fields.anthropic.input.value.trim()) keys.anthropic = fields.anthropic.input.value.trim();
    if (fields.pandaprobe.input.value.trim()) {
      keys.pandaprobe = fields.pandaprobe.input.value.trim();
      const proj = fields.pandaprobe.extra.value.trim();
      if (proj) keys.pandaprobe_project = proj;
    }
    if (fields.latchkey.input.value.trim()) keys.latchkey = fields.latchkey.input.value.trim();
    if (fields.repair.input.value.trim()) keys.repair_model = fields.repair.input.value.trim();
    return keys;
  }

  let inflight = false;
  async function validate(only) {
    if (inflight) return;
    const keys = collectKeys();
    const wanted = { anthropic: "anthropic", pandaprobe: "pandaprobe", latchkey: "latchkey" };
    const names = only ? [only] : Object.keys(wanted).filter((n) => keys[n]);
    const body = {};
    for (const n of names) {
      if (!keys[n]) continue;
      body[n] = keys[n];
      if (n === "pandaprobe" && keys.pandaprobe_project) body.pandaprobe_project = keys.pandaprobe_project;
    }
    if (Object.keys(body).length === 0) return;
    for (const n of names) if (keys[n]) setStatus(n, null, "checking…");
    inflight = true;
    try {
      const res = await postJSON("/api/setup", { keys: body });
      const v = res.validation || {};
      for (const n of names) {
        if (!v[n]) continue;
        if (v[n].ok) {
          setStatus(n, "ok", n === "pandaprobe" ? "✓ project ok" : "✓ valid");
        } else {
          setStatus(n, "bad", `✗ ${v[n].detail || `status ${v[n].status}`}`);
        }
      }
    } catch (err) {
      for (const n of names) setStatus(n, "bad", `✗ ${err.message}`);
    } finally {
      inflight = false;
    }
  }

  function field(name, label, chipText, chipClass, hint, opts = {}) {
    const input = el("input", {
      class: "key", type: "text", spellcheck: "false", autocomplete: "off",
      placeholder: opts.placeholder || "", value: opts.value || "",
    });
    const status = statusEl();
    fields[name] = { input, status };
    const inputs = [input];
    if (opts.project) {
      const extra = el("input", {
        class: "project", type: "text", spellcheck: "false",
        placeholder: "project name",
      });
      fields[name].extra = extra;
      inputs.push(extra);
      extra.addEventListener("blur", () => { if (input.value.trim()) validate(name); });
    }
    if (opts.staticStatus) {
      status.style.display = "flex";
      status.textContent = opts.staticStatus;
    } else {
      input.addEventListener("blur", () => { if (input.value.trim()) validate(name); });
    }
    return el("div", { class: "setup-field" },
      el("div", { class: "label-row" },
        el("span", { class: "label" }, label),
        el("span", { class: `req-chip ${chipClass}` }, chipText)),
      el("div", { class: "inputs" }, inputs, status),
      hint ? el("div", { class: "hint" }, hint) : null);
  }

  const saveBtn = el("button", { class: "btn primary" }, "Save & index repo →");
  saveBtn.addEventListener("click", async () => {
    const keys = collectKeys();
    saveBtn.textContent = "Saving…";
    try {
      if (Object.keys(keys).length) await postJSON("/api/setup", { action: "write", keys });
      location.hash = "#/graph";
    } catch (err) {
      saveBtn.textContent = "Save & index repo →";
      setStatus("anthropic", "bad", `✗ ${err.message}`);
    }
  });

  const card = el("div", { class: "card setup-card" },
    el("div", { class: "setup-head" },
      el("div", { class: "title" }, "Set up your custodian"),
      el("div", { class: "sub" },
        "Keys are validated live and written to ", el("span", { class: "mono" }, ".env"),
        " in your repo — local file, never uploaded."),
      el("div", { class: "explainer-row", style: { marginTop: "6px" } },
        explainer(
          "Paste your keys here. Each one is checked against the real service before anything is saved, so you find out now if a key is wrong.",
          "They are written to a .env file in this repo, which is git-ignored. Nothing is uploaded, and Gusset has no server of its own.",
          "Only the Anthropic key is required. Skip the others and everything still runs \u2014 you just don\u2019t get the extras they turn on.",
        ))),
    el("div", { class: "setup-body" },
      field("anthropic", "Anthropic API key", "REQUIRED", "filled",
        "Powers the workflows. Checked with a zero-token models call.",
        { placeholder: "sk-ant-api03-…" }),
      field("pandaprobe", "PandaProbe", "RECOMMENDED", "",
        "Traces, scores, self-healing. Free tier at app.pandaprobe.com — skip and everything still runs, scores stay local.",
        { placeholder: "sk_pp_…", project: true }),
      field("latchkey", "Latchkey", "RECOMMENDED", "",
        "Runners for CI + clean-machine verification. Errors name the missing scope, never just \"invalid\".",
        { placeholder: "lk_live_…" }),
      field("repair", "Self-healing repair model", "OPTIONAL", "dim", null,
        { value: "anthropic/claude-sonnet-5", staticStatus: "uses key above" })),
    el("div", { class: "setup-foot" },
      el("div", { class: "env-note" }, "writes → ", el("b", {}, ".env"), " (gitignored)"),
      el("div", { class: "actions" },
        el("button", { class: "btn", onclick: () => { location.hash = "#/graph"; } }, "Skip for now"),
        saveBtn)));

  container.append(el("div", { class: "setup-wrap dotbg" }, card));
}
