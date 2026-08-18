#!/usr/bin/env python3
"""Generate the architecture diagrams as Gusset-themed SVGs.

Single source of truth for the diagrams in docs/explanation/architecture.md
(committed to docs/assets/) and the design-canvas boards. Edit here, re-run:

    python design/architecture/gen_diagrams.py
"""

import html
from pathlib import Path

INK = "#22211d"; PANEL = "#fdfcf8"; GROUND = "#f4f1ea"; LINE = "#d9d3c4"
RUST = "#b4551e"; PASS = "#2e7d4f"; DROP = "#c23934"
MUTED = "#6b675c"; FAINT = "#8a8577"
SANS = "Archivo, system-ui, sans-serif"
MONO = "'Spline Sans Mono', ui-monospace, Menlo, monospace"

OUT = Path(__file__).resolve().parents[2] / "docs" / "assets"


class SVG:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.parts: list[str] = []

    def title(self, x, y, text, sub=""):
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{SANS}" font-weight="800" '
            f'font-size="21" fill="{INK}">{text}</text>')
        if sub:
            self.parts.append(
                f'<text x="{x}" y="{y+22}" font-family="{MONO}" font-size="11.5" '
                f'fill="{FAINT}">{sub}</text>')

    def node(self, x, y, w, h, head, subs=(), border=INK, dash="", shadow=True,
             head_color=None, bw=1.5):
        if shadow and not dash:
            self.parts.append(
                f'<rect x="{x+4}" y="{y+4}" width="{w}" height="{h}" rx="5" fill="{LINE}"/>')
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" '
            f'fill="{PANEL}" stroke="{border}" stroke-width="{bw}"{d}/>')
        self.parts.append(
            f'<text x="{x+w/2}" y="{y+27}" text-anchor="middle" font-family="{SANS}" '
            f'font-weight="600" font-size="15.5" fill="{head_color or INK}">{html.escape(head)}</text>')
        for i, s in enumerate(subs):
            self.parts.append(
                f'<text x="{x+w/2}" y="{y+48+i*17}" text-anchor="middle" '
                f'font-family="{MONO}" font-size="11" fill="{MUTED}">{html.escape(s)}</text>')

    def edge(self, pts, color=INK, dash="", width=1.7, marker=True):
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts)
        m = f' marker-end="url(#m-{color[1:]})"' if marker else ""
        dd = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dd}{m}/>')

    def pill(self, cx, cy, text, color=MUTED, border=LINE):
        w = int(len(text) * 6.55) + 18
        self.parts.append(
            f'<rect x="{cx-w/2}" y="{cy-11}" width="{w}" height="22" rx="4" '
            f'fill="{PANEL}" stroke="{border}" stroke-width="1"/>')
        self.parts.append(
            f'<text x="{cx}" y="{cy+4}" text-anchor="middle" font-family="{MONO}" '
            f'font-size="10.5" fill="{color}">{html.escape(text)}</text>')

    def group(self, x, y, w, h, label, color=FAINT):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="none" '
            f'stroke="{color}" stroke-width="1.3" stroke-dasharray="6 5"/>')
        self.parts.append(
            f'<text x="{x+12}" y="{y-8}" font-family="{MONO}" font-size="11" '
            f'letter-spacing="1.5" fill="{color}">{label}</text>')

    def chip(self, x, y, text, color=MUTED):
        w = int(len(text) * 6.55) + 18
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="24" rx="4" fill="{PANEL}" '
            f'stroke="{INK}" stroke-width="1.2"/>')
        self.parts.append(
            f'<text x="{x+w/2}" y="{y+16}" text-anchor="middle" font-family="{MONO}" '
            f'font-size="10.5" fill="{color}">{html.escape(text)}</text>')
        return w

    def render(self) -> str:
        markers = "".join(
            f'<marker id="m-{c[1:]}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            f'markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>'
            for c in (INK, RUST, PASS, DROP, FAINT))
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">'
            f'<defs>{markers}<pattern id="dots" width="24" height="24" '
            f'patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="{LINE}"/>'
            f'</pattern></defs>'
            f'<rect width="{self.w}" height="{self.h}" fill="{GROUND}"/>'
            f'<rect width="{self.w}" height="{self.h}" fill="url(#dots)"/>'
            + "".join(self.parts) + "</svg>")


def system_context() -> str:
    s = SVG(1140, 700)
    s.title(40, 46, "System context",
            "solid = deterministic spine (works with zero credentials) · dashed = optional layers")

    # top pipeline
    s.node(40, 100, 180, 92, "events", ("PR opened · push", "cron · manual"))
    s.node(290, 100, 240, 92, "supervisor",
           ("deterministic guards", "budgets · autonomy ladder"))
    s.node(600, 100, 240, 92, "workflows",
           ("impact · atlas · docs-drift", "typed state · checkpoints"))
    s.node(910, 100, 190, 92, "deliverables",
           ("PR comment + diagram", "PRs · reports"))
    s.edge([(220, 146), (290, 146)])
    s.edge([(530, 146), (600, 146)])
    s.edge([(840, 146), (910, 146)])
    s.pill(565, 216, "only if guards pass — the graph decides", RUST, RUST)

    # truth lane
    s.node(40, 310, 180, 88, "your code", ("+ package manifests",))
    s.node(290, 310, 180, 88, "indexer", ("tree-sitter · no LLM",))
    s.node(540, 310, 180, 88, "graph.db", ("symbols · proven edges", "packages + versions"))
    s.node(790, 310, 180, 88, "oracle", ("edge_exists()", "closures · scores"),
           border=RUST, head_color=RUST)
    s.edge([(220, 354), (290, 354)])
    s.edge([(470, 354), (540, 354)])
    s.edge([(720, 354), (790, 354)])
    s.edge([(880, 310), (880, 240), (760, 240), (760, 192)], color=RUST)
    s.pill(878, 262, "verifies every claim before you see it", RUST, RUST)

    # committed state
    s.group(40, 490, 470, 160, "COMMITTED STATE — IN YOUR REPO")
    x = 60
    for t in ("gusset.toml", "ladder.jsonl", "drift-allowlist", ".gusset/runs/"):
        x += s.chip(x, 520, t) + 12
    s.parts.append(
        f'<text x="62" y="576" font-family="{MONO}" font-size="10.5" fill="{MUTED}">'
        f'config · every autonomy decision with its reason ·</text>')
    s.parts.append(
        f'<text x="62" y="593" font-family="{MONO}" font-size="10.5" fill="{MUTED}">'
        f'curated externals · replayable run event logs</text>')
    s.edge([(275, 490), (275, 460), (410, 460), (410, 192)], color=FAINT)
    s.pill(348, 460, "config + score ledger", FAINT)

    # serve
    s.node(560, 500, 250, 110, "gusset serve",
           ("localhost-only canvas", "graph · replays · ladder", "drift · setup"))
    s.edge([(630, 398), (630, 435), (650, 435), (650, 500)], color=FAINT)
    s.pill(630, 470, "reads, never uploads", FAINT)

    # observability
    s.group(860, 490, 240, 170, "OPTIONAL")
    s.node(880, 512, 200, 60, "PandaProbe", ("traces · scores · evals",),
           dash="5 4", border=FAINT, shadow=False)
    s.node(880, 585, 200, 60, "self-healing harness", ("repair agent · rules",),
           dash="5 4", border=FAINT, shadow=False)
    s.edge([(800, 192), (800, 240), (960, 240), (960, 512)], color=FAINT, dash="5 4")
    return s.render()


def impact_graph() -> str:
    s = SVG(920, 730)
    s.title(40, 46, "The impact workflow",
            "the graph decides WHO is affected — the model only writes WHY")

    cx, w = 300, 260
    s.node(cx, 90, w, 74, "resolve_seeds", ("diff / symbol → graph symbols",))
    s.node(cx, 224, w, 82, "expand_ring",
           ("graph computes ring N", "model explains each edge"))
    s.node(cx, 366, w, 82, "verify_gate",
           ("edge exists in graph → keep", "else drop + log"))
    s.node(cx, 508, w, 74, "synthesize", ("report from verified only",))
    s.node(cx, 622, w, 74, "◇ human gate",
           ("terminal approve · PR review",), border=RUST, head_color=RUST)
    for y1, y2 in ((164, 224), (306, 366), (448, 508), (582, 622)):
        s.edge([(cx + w / 2, y1), (cx + w / 2, y2)])

    # halt branch
    s.node(60, 90, 180, 74, "halt", ("honest no-op — never", "analyze invented symbols"),
           dash="5 4", border=DROP, shadow=False, head_color=DROP)
    s.edge([(cx, 127), (240, 127)], color=DROP, dash="5 4")
    s.pill(270, 108, "no seeds", DROP, DROP)

    # loop
    s.edge([(cx + w, 407), (660, 407), (660, 265), (cx + w, 265)], color=RUST)
    s.pill(660, 336, "frontier remains · depth < 4", RUST, RUST)

    # oracle
    s.node(60, 366, 180, 82, "oracle", ("graph.db queries —", "deterministic, no LLM"),
           border=RUST, head_color=RUST)
    s.edge([(240, 407), (cx, 407)], color=RUST)

    # dropped log
    s.node(680, 470, 200, 66, "dropped claims", ("logged, never hidden",),
           dash="5 4", border=DROP, shadow=False, head_color=DROP)
    s.edge([(cx + w, 430), (680, 496)], color=DROP, dash="5 4")

    # guards
    s.parts.append(
        f'<text x="690" y="96" font-family="{MONO}" font-size="11" letter-spacing="1.5" '
        f'fill="{FAINT}">GUARDS — CODE, NOT VIBES</text>')
    for i, t in enumerate(("depth ≤ 4", "fan-out ≤ 40 → aggregate",
                           "8 retries + fallback tier")):
        s.chip(690, 110 + i * 34, t)

    s.pill(430, 716, "output: report + deterministic oracle scores", MUTED)
    return s.render()


def ladder() -> str:
    s = SVG(980, 470)
    s.title(40, 46, "The autonomy ladder", "permissions are earned with scores, not configured")

    xs = (40, 280, 520, 760)
    heads = ("REPORT", "COMMENT", "PROPOSE", "ACT")
    subs = (("write files only",), ("comment on PRs",), ("open PRs",),
            ("auto-merge classes", "human-granted only"))
    for x, h, sb in zip(xs, heads, subs):
        dash = "6 5" if h == "ACT" else ""
        s.node(x, 170, 180, 96, h, sb, dash=dash,
               border=FAINT if h == "ACT" else INK, shadow=not dash)

    for x1, x2 in ((220, 280), (460, 520)):
        s.edge([(x1, 200), (x2, 200)], color=PASS)
    s.edge([(700, 218), (760, 218)], color=FAINT, dash="6 5")
    for x1, x2 in ((280, 220), (520, 460)):
        s.edge([(x1, 240), (x2, 240)], color=DROP)

    s.pill(380, 120, "promote: 15 consecutive runs with every score ≥ 0.9", PASS, PASS)
    s.pill(380, 310, "demote: 3 of the last 5 runs below 0.8 — automatic", DROP, DROP)
    s.pill(760, 120, "gusset.toml only — never the ladder", FAINT)

    for i, t in enumerate((
            "rate metrics are normalized lower-is-better before scoring — a 0.0 drop rate is a perfect run",
            "errored runs (provider weather) are never scored: missing data is not bad quality",
            "every transition is one JSON line in .gusset/ladder.jsonl, committed to the repo")):
        s.parts.append(
            f'<text x="40" y="{382 + i * 22}" font-family="{MONO}" font-size="11.5" '
            f'fill="{MUTED}">· {t}</text>')
    return s.render()


def healing() -> str:
    s = SVG(1000, 600)
    s.title(40, 46, "The self-healing loop",
            "a second agent repairs the first — with evidence gates, never self-approval")

    s.node(60, 110, 210, 82, "workflow turn", ("turn hook fires", "run continues unblocked"))
    s.node(395, 110, 210, 82, "trajectory scoring", ("score tiers +", "oracle outcome verifier"))
    s.node(730, 110, 210, 82, "diagnostic notice", ("filesystem mailbox —", "the workflow never reads it"))
    s.node(730, 330, 210, 82, "repair agent", ("separate model, separate", "context · diagnoses the stall"),
           border=RUST, head_color=RUST)
    s.node(395, 330, 210, 82, "candidate rule", ("rules/*.md — committed,", "human-readable"))
    s.node(60, 330, 210, 82, "replay validation", ("same commit, same seeds —", "oracle-scored evidence"))

    s.edge([(270, 151), (395, 151)])
    s.edge([(605, 151), (730, 151)])
    s.edge([(835, 192), (835, 330)])
    s.edge([(730, 371), (605, 371)])
    s.edge([(395, 371), (270, 371)])
    s.edge([(165, 330), (165, 192)], color=PASS)
    s.pill(165, 262, "validated → active · next runs read it", PASS, PASS)
    s.pill(500, 262, "no rule reaches active without replayed evidence", MUTED)

    for i, t in enumerate((
            "trajectory gate: fires on stalls and regressions across runs, not isolated low scores",
            "the workflow's only exposure: four read-only rule tools and a one-sentence preamble",
            "failed candidates are retired with journaled reasoning — .gusset/harness/ is auditable in-repo")):
        s.parts.append(
            f'<text x="60" y="{490 + i * 22}" font-family="{MONO}" font-size="11.5" '
            f'fill="{MUTED}">· {t}</text>')
    return s.render()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("arch-system", system_context), ("arch-impact", impact_graph),
                     ("arch-ladder", ladder), ("arch-healing", healing)):
        path = OUT / f"{name}.svg"
        path.write_text(fn())
        print(f"wrote {path} ({path.stat().st_size // 1024} KB)")
