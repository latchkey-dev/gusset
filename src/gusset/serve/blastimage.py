"""Blast-radius image for PR comments: the impact result as one SVG.

Pure-Python SVG generation — CI runners need no browser, no matplotlib.
GitHub renders SVG in comments when committed as a repo blob or attached
via the asset URL; we also emit PNG via a data-URI-free fallback: the
Action commits the SVG under .gusset/out/ on the PR branch when it can,
else the comment carries a Mermaid-free ASCII summary (never a broken
image link).

Layout mirrors the approved Impact view: seed center, verified nodes on
depth rings (pass-green), dropped claims outside the outer ring in
drop-red with an X. Paper theme — PR comments are on white GitHub.
"""

from __future__ import annotations

import html
import math

INK = "#22211d"
LINE = "#d9d3c4"
RUST = "#b4551e"
PASS = "#2e7d4f"
DROP = "#c23934"
PAPER = "#f4f1ea"
PANEL = "#fdfcf8"
MUTED = "#6b675c"
FAINT = "#8a8577"

W, H = 880, 560
CX, CY = 340, 280
RING_STEP = 105


def blast_svg(seeds: list[str], verified: list[dict], dropped: list[dict]) -> str:
    """Render the impact result. Caps at 24 verified nodes, aggregating the
    rest into a count badge — a PR comment is a summary, not a wall."""
    shown = verified[:24]
    overflow = len(verified) - len(shown)
    max_depth = max((c.get("depth", 1) for c in shown), default=1)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="ui-monospace,Menlo,monospace">',
        f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
        f'<rect x="1" y="1" width="{W-2}" height="{H-2}" fill="none" '
        f'stroke="{INK}" stroke-width="2"/>',
    ]
    # drafting dots
    parts.append(f'<g fill="{LINE}">')
    for gx in range(24, W - 200, 26):
        for gy in range(24, H - 20, 26):
            parts.append(f'<circle cx="{gx}" cy="{gy}" r="1"/>')
    parts.append("</g>")

    # depth rings
    for d in range(1, max_depth + 1):
        r = RING_STEP * d
        parts.append(
            f'<circle cx="{CX}" cy="{CY}" r="{r}" fill="none" stroke="{FAINT}" '
            f'stroke-width="1.2" stroke-dasharray="6 7"/>'
        )
        parts.append(
            f'<text x="{CX - r + 8}" y="{CY - 8}" font-size="10" '
            f'fill="{FAINT}">DEPTH {d}</text>'
        )

    # verified nodes ring-by-ring
    by_depth: dict[int, list[dict]] = {}
    for c in shown:
        by_depth.setdefault(c.get("depth", 1), []).append(c)
    positions: dict[str, tuple[float, float]] = {}
    for depth, claims in by_depth.items():
        r = RING_STEP * depth
        for i, c in enumerate(claims):
            angle = (2 * math.pi * i / len(claims)) - math.pi / 2 + depth * 0.35
            x, y = CX + r * math.cos(angle), CY + r * math.sin(angle)
            positions[c["qualname"]] = (x, y)

    for c in shown:  # edges first, under nodes
        x, y = positions[c["qualname"]]
        vx, vy = positions.get(c.get("via", ""), (CX, CY))
        parts.append(
            f'<line x1="{vx:.0f}" y1="{vy:.0f}" x2="{x:.0f}" y2="{y:.0f}" '
            f'stroke="{RUST}" stroke-width="1.6"/>'
        )
    for i, c in enumerate(dropped[:4]):
        x, y = W - 205, 90 + i * 46
        parts.append(
            f'<line x1="{CX}" y1="{CY}" x2="{x:.0f}" y2="{y:.0f}" stroke="{DROP}" '
            f'stroke-width="1.4" stroke-dasharray="5 4" opacity="0.55"/>'
        )
        parts.append(
            f'<g><circle cx="{x:.0f}" cy="{y:.0f}" r="8" fill="#fbeae9" '
            f'stroke="{DROP}" stroke-width="1.6"/>'
            f'<path d="M{x-4:.0f} {y-4:.0f} l8 8 M{x+4:.0f} {y-4:.0f} l-8 8" '
            f'stroke="{DROP}" stroke-width="1.5"/></g>'
        )

    for c in shown:
        x, y = positions[c["qualname"]]
        parts.append(
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" fill="{PANEL}" '
            f'stroke="{PASS}" stroke-width="2"/>'
        )
        label = html.escape(_short(c["qualname"]))
        parts.append(
            f'<text x="{x:.0f}" y="{y + 22:.0f}" font-size="9.5" fill="{INK}" '
            f'text-anchor="middle">{label}</text>'
        )

    # seed
    parts.append(f'<circle cx="{CX}" cy="{CY}" r="13" fill="{RUST}"/>')
    seed_label = html.escape(_short(seeds[0]) if seeds else "seed")
    parts.append(
        f'<text x="{CX}" y="{CY + 30}" font-size="11" fill="{RUST}" '
        f'text-anchor="middle" font-weight="bold">{seed_label}</text>'
    )

    # legend / tally card
    lx = W - 218
    parts.append(
        f'<rect x="{lx}" y="{H - 150}" width="200" height="132" fill="{PANEL}" '
        f'stroke="{INK}" stroke-width="1.5"/>'
    )
    tally = [
        (PASS, f"{len(verified)} verified"),
        (DROP, f"{len(dropped)} dropped at the gate"),
        (FAINT, f"{max_depth} ring(s)"),
    ]
    if overflow > 0:
        tally.append((MUTED, f"+{overflow} not drawn"))
    for i, (color, text) in enumerate(tally):
        y = H - 126 + i * 24
        parts.append(f'<circle cx="{lx + 16}" cy="{y}" r="5" fill="{color}"/>')
        parts.append(
            f'<text x="{lx + 30}" y="{y + 4}" font-size="11" '
            f'fill="{INK}">{html.escape(text)}</text>'
        )
    parts.append(
        f'<text x="{lx}" y="{H - 160}" font-size="10" fill="{FAINT}">'
        f"GUSSET · every edge verified in the code graph</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _short(qualname: str, keep: int = 3) -> str:
    parts = qualname.split(".")
    return ".".join(parts[-keep:]) if len(parts) > keep else qualname
