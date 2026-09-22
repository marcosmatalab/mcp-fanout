"""Render the observation chain as an SVG: what the proxy sees, and what it does not.

    make chain-svg      # writes docs/figures/observation-chain.svg

One drawing, and only one. It is the picture that makes threat 19 obvious without reading a
paragraph: a tool call enters a server process, the process may reach a third party through any of
several HTTP clients, an environment-variable proxy observes only the clients that chose to honour
two environment variables, and the packet capture underneath observes all of them. Every other
diagram this repository could carry (the harness architecture, the file layout) says something the
status table already says, so it is not drawn.

The counts on the drawing are read from the committed concurrent figure, not typed here: the
number of components the proxy observed is a measurement, and a measurement inside a picture is
still a published figure under rule 6. The structure of the chain is drawn, the figures are read.

Colours follow the same rule as the honesty curve: the file is its own document when a README
references it, so it carries its own stylesheet with a dark-scheme block and declares no
background. See tools/render_honesty_curve.py for why `currentColor` does not work here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIGURE = REPO / "docs" / "figures" / "20260919T194649Z-concurrent.json"

WIDTH, HEIGHT = 800, 430

# Geometry, named so the routing below reads as a layout and not as a pile of constants.
COL_A_X, COL_A_W = 24, 150          # the call and the process it enters
COL_B_X, COL_B_W = 214, 240         # the three kinds of HTTP client a server process may use
COL_C_X, COL_C_W = 506, 150         # the proxy, and the third party behind it
BOX_H = 62
ROW_Y = (60, 150, 240)              # the three client rows
BYPASS_X = (708, 734)               # the lanes the proxy never sees, routed clear of the boxes

STYLE = """<style>
  text { fill: #1f2328; }
  text.muted { fill: #57606a; }
  text.blind { fill: #d1603d; }
  rect.node { fill: none; stroke: #57606a; }
  rect.blind { fill: none; stroke: #d1603d; }
  line.edge, path.edge { stroke: #57606a; fill: none; }
  line.blind, path.blind { stroke: #d1603d; fill: none; }
  rect.band { fill: #57606a; fill-opacity: 0.06; stroke: #57606a; stroke-opacity: 0.35; }
  @media (prefers-color-scheme: dark) {
    text { fill: #e6edf3; }
    text.muted { fill: #9198a1; }
    rect.node { stroke: #9198a1; }
    line.edge, path.edge { stroke: #9198a1; }
    rect.band { fill: #9198a1; fill-opacity: 0.08; stroke: #9198a1; stroke-opacity: 0.35; }
  }
</style>"""


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def observed_components() -> int:
    """How many components the proxy observed, read from the committed concurrent figure.

    A count inside a picture is still a published figure, so it comes from the artifact and not
    from this file. `egress_unobserved` sits beside it in the same block, which is what makes
    "observed" a statement about the instrument rather than about the servers.
    """
    figure = json.loads(FIGURE.read_text(encoding="utf-8"))
    number_3 = next(n for n in figure["numbers"] if n["number"] == 3)
    return number_3["observability"]["proxy_observed"]


def _box(x: float, y: float, w: float, h: float, label: str, sub: str = "",
         blind: bool = False) -> list[str]:
    cls = "blind" if blind else "node"
    out = [f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="6" '
           f'stroke-width="1.5"/>']
    text_cls = ' class="blind"' if blind else ""
    baseline = y + h / 2 + (0 if not sub else -4)
    out.append(f'<text{text_cls} x="{x + w / 2}" y="{baseline:.1f}" font-size="13" '
               f'text-anchor="middle">{_escape(label)}</text>')
    if sub:
        out.append(f'<text class="muted" x="{x + w / 2}" y="{baseline + 17:.1f}" font-size="11" '
                   f'text-anchor="middle">{_escape(sub)}</text>')
    return out


def render() -> str:
    proxy_observed = observed_components()
    parts: list[str] = []
    add = parts.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" font-family="-apple-system, BlinkMacSystemFont, '
        f'Segoe UI, Helvetica, Arial, sans-serif" role="img" aria-label="A tool call reaches a '
        f'third party through one of three kinds of HTTP client. The environment-variable proxy '
        f'observes one kind. The packet capture underneath observes all of them.">')
    add(STYLE)
    add('<title>The observation chain</title>')
    add('<desc>A tool call enters a server process. The process can reach a third party through '
        'a proxy-honouring client, through Node\'s global fetch, which ignores the proxy '
        'variables, or through a pinned or custom client. The proxy sees only the first kind. '
        'The packet capture sees every outbound connection, which is how the blind client was '
        'found.</desc>')
    add('<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>')

    add('<text x="24" y="26" font-size="16" font-weight="600">What the proxy observes is not '
        'what the agent sent</text>')

    # Column A: the call, and the process it enters.
    parts += _box(COL_A_X, 60, COL_A_W, 52, "tool call", "MCP, over stdio")
    parts += _box(COL_A_X, 150, COL_A_W, BOX_H, "server process", "one pid, several clients")
    centre_a = COL_A_X + COL_A_W / 2
    add(f'<line class="edge" x1="{centre_a}" y1="112" x2="{centre_a}" y2="150" '
        f'stroke-width="1.5" marker-end="url(#arrow)"/>')

    # Column B: the three kinds of client. Two of them are invisible to an env-var proxy.
    clients = [
        ("proxy-honouring client", "requests, axios, curl", False),
        ("Node global fetch, undici", "ignores HTTP(S)_PROXY", True),
        ("pinned or custom client", "if one exists, unmeasured", True),
    ]
    right_b = COL_B_X + COL_B_W
    for y, (label, sub, blind) in zip(ROW_Y, clients):
        parts += _box(COL_B_X, y, COL_B_W, BOX_H, label, sub, blind)
        add(f'<line class="edge" x1="{COL_A_X + COL_A_W}" y1="181" x2="{COL_B_X}" '
            f'y2="{y + BOX_H / 2}" stroke-width="1.5" marker-end="url(#arrow)"/>')

    # Column C: the proxy on the observed path, the third party at the end of every path.
    parts += _box(COL_C_X, 60, COL_C_W, BOX_H, "the proxy",
                  f"observed {proxy_observed} components")
    parts += _box(COL_C_X, 240, COL_C_W, BOX_H, "third party", "answers either way")
    centre_c = COL_C_X + COL_C_W / 2
    add(f'<line class="edge" x1="{right_b}" y1="91" x2="{COL_C_X}" y2="91" stroke-width="1.5" '
        f'marker-end="url(#arrow)"/>')
    add(f'<line class="edge" x1="{centre_c}" y1="122" x2="{centre_c}" y2="240" '
        f'stroke-width="1.5" marker-end="url(#arrow)"/>')

    # The two bypass lanes: out to the right of everything, then back into the third party. They
    # are drawn around the proxy rather than through it, because that is what the traffic does.
    # The lower lane detours under the third party rather than crossing it: a line drawn through
    # a box reads as entering the box, which is the one thing this traffic does not do on the way.
    right_c = COL_C_X + COL_C_W
    add(f'<path class="blind" d="M{right_b},{ROW_Y[1] + BOX_H / 2} H{BYPASS_X[0]} V258 '
        f'H{right_c}" stroke-width="1.5" stroke-dasharray="6 4" marker-end="url(#arrow)"/>')
    add(f'<path class="blind" d="M{right_b},{ROW_Y[2] + BOX_H / 2} H{right_b + 22} V318 '
        f'H{BYPASS_X[1]} V288 H{right_c}" stroke-width="1.5" stroke-dasharray="6 4" '
        f'marker-end="url(#arrow)"/>')
    add(f'<text class="blind" x="{right_b + 8}" y="{ROW_Y[1] + BOX_H / 2 - 8:.0f}" '
        f'font-size="11">straight past the proxy</text>')

    # The capture layer underneath: the only one that sees every outbound connection.
    band_w = COL_C_X + COL_C_W - COL_A_X
    add(f'<rect class="band" x="{COL_A_X}" y="336" width="{band_w}" height="48" rx="6" '
        f'stroke-width="1.5"/>')
    band_centre = COL_A_X + band_w / 2
    add(f'<text x="{band_centre}" y="359" font-size="13" text-anchor="middle">packet capture: '
        f'every outbound SYN, whatever the client decided</text>')
    add(f'<text class="muted" x="{band_centre}" y="376" font-size="11" text-anchor="middle">'
        f'make backstop. The layer that found the blind client, and the only judge of what is '
        f'still missing</text>')

    footer = ("Dashed: traffic an environment-variable proxy cannot see. Solid: traffic it can. "
              "The proxy is a configuration a client may decline, not a boundary.")
    for index, line in enumerate(_wrap(footer, width=106)):
        add(f'<text class="muted" x="{COL_A_X}" y="{404 + index * 14}" font-size="11">'
            f'{_escape(line)}</text>')
    add('</svg>')
    return "\n".join(parts) + "\n"


def main() -> int:
    sys.stdout.write(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
