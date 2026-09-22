"""Render the honesty curve as an SVG, from the same command that publishes the numbers.

    make curve-svg      # writes docs/figures/honesty-curve.svg

Why this exists at all: the curve is the repository's whole argument about method (three
measurements of one quantity, each taken after an observability defect was fixed, each one lower
than the last) and a reader who never clones cannot run `make honesty-curve`. An image is the only
form of that argument that survives the first sixty seconds.

Why it is generated and not drawn: a hand-drawn figure is a number without a command behind it,
which rule 6 forbids, and it goes stale silently, which is the failure gate 3 exists to catch. This
script reads `tools/honesty_curve.py` on stdout and nothing else, so the picture cannot disagree
with the figure. `make figures-check` regenerates it and fails on a non-empty diff.

Why no plotting library: the measurement core is standard-library only on purpose (see
pyproject.toml). A renderer that pulled in matplotlib would put a transitive dependency in the path
of a published artifact, which is the supply-chain failure this project studies. The cost is about
a hundred lines of string formatting, paid once.

Why these colours: GitHub renders README images on a light or a dark background depending on the
reader, and an SVG with a white background shows as a patch on the dark theme. `currentColor` does
NOT solve it: an SVG referenced by an `img` tag is its own document and inherits nothing from the
page, so `currentColor` resolves to black and the figure disappears on the dark theme. This file
therefore carries its own stylesheet with a `prefers-color-scheme` block, declares no background at
all, and uses one accent chosen to hold contrast against both. Checked by rendering the file over
both backgrounds, not by reading the specification.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Canvas. Chosen so the figure is legible at the width GitHub gives a README image without the
# reader zooming, and so the three captions fit on two lines each at 11px.
WIDTH, HEIGHT = 760, 412
LEFT, RIGHT, TOP, BOTTOM = 92, 40, 46, 150
PLOT_W = WIDTH - LEFT - RIGHT
# The points are inset from the frame: a data point on the axis clips its own label and its
# caption, and a label a reader has to guess at is worse than a narrower plot.
INSET = 76
PLOT_H = HEIGHT - TOP - BOTTOM
Y_MIN, Y_MAX = 0.6, 1.0          # the data lives in [0.6579, 0.8947]; the frame is not zoomed
ACCENT = "#d1603d"               # readable on both GitHub themes, and not the green of a pass
CAPTION_CHARS = 30

# The stylesheet travels inside the file, because the file is read as its own document.
#
# No custom properties: a CSS variable is resolved by browsers and dropped by several standalone
# SVG rasterizers, and a figure that renders black on black in one of them is a figure nobody can
# check. Every colour is therefore written twice, once per scheme. And every element the sheet
# colours takes a class: a CSS rule beats a presentation attribute, so `text { fill: ... }` would
# silently repaint the accent labels, which is exactly what it did the first time.
STYLE = """<style>
  text { fill: #1f2328; }
  text.muted { fill: #57606a; }
  text.value { fill: #d1603d; }
  line.grid { stroke: #d8dee4; }
  line.axis { stroke: #57606a; stroke-opacity: 0.6; }
  line.threshold { stroke: #57606a; }
  @media (prefers-color-scheme: dark) {
    text { fill: #e6edf3; }
    text.muted { fill: #9198a1; }
    line.grid { stroke: #30363d; }
    line.axis { stroke: #9198a1; stroke-opacity: 0.6; }
    line.threshold { stroke: #9198a1; }
  }
</style>"""


def _fmt(value: float) -> str:
    """Two decimals, fixed, so the file is byte-identical on every machine."""
    return f"{value:.2f}"


def _y(fraction: float) -> float:
    return TOP + PLOT_H * (Y_MAX - fraction) / (Y_MAX - Y_MIN)


def _x(index: int, total: int) -> float:
    if total == 1:
        return LEFT + PLOT_W / 2
    span = PLOT_W - 2 * INSET
    return LEFT + INSET + span * index / (total - 1)


def _first_clause(text: str) -> str:
    """The head of a blind-spot sentence, which is the part that names the thing.

    The sentences are written for the JSON output and carry their own justification after a comma
    or a colon. A caption under a data point has room for the name only, and the full sentence is
    one `make honesty-curve` away.
    """
    cuts = [text.index(s) for s in (", ", ": ") if s in text]
    return text[:min(cuts)] if cuts else text


def _wrap(text: str, width: int = CAPTION_CHARS) -> list[str]:
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


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))


def _captions(points: list[dict]) -> list[str]:
    """What blindness was removed before each point was measured, derived from the data.

    Not a hand-written list: the difference between consecutive `instrument_was_blind_to` sets is
    exactly the defect that was fixed between the two runs, so the caption cannot drift from the
    figure it captions.
    """
    out = []
    for index, point in enumerate(points):
        if index == 0:
            out.append("first measurement, two blind spots still open")
            continue
        previous = points[index - 1]["instrument_was_blind_to"]
        removed = [b for b in previous if b not in point["instrument_was_blind_to"]]
        if not removed:
            out.append("no blind spot removed")
        else:
            out.append("fixed: " + ", ".join(_first_clause(r) for r in removed))
    return out


def curve_json() -> dict:
    """The figure itself, from its own command. Never transcribed."""
    result = subprocess.run([sys.executable, str(REPO / "tools" / "honesty_curve.py")],
                            cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit("make honesty-curve failed; there is no curve to render")
    return json.loads(result.stdout)


def render(data: dict) -> str:
    points = data["points"]
    threshold = data["threshold_preregistered"]
    captions = _captions(points)
    parts: list[str] = []
    add = parts.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" font-family="-apple-system, BlinkMacSystemFont, '
        f'Segoe UI, Helvetica, Arial, sans-serif" role="img" '
        f'aria-label="Every observability fix lowered the headline figure: '
        f'{", ".join(_fmt(p["fraction"]) for p in points)}, against a pre-registered threshold '
        f'of {threshold}">')
    add(STYLE)
    add('<title>The honesty curve</title>')
    add('<desc>Three measurements of one quantity, in the order taken, each after an '
        'observability defect in the instrument was fixed. The figure fell every time and ended '
        'below the threshold sealed before any measurement existed.</desc>')

    # Y axis: gridlines every 0.1, labelled. Drawn first so the data sits on top of them.
    add('<g stroke-width="1">')
    tick = Y_MIN
    while tick <= Y_MAX + 1e-9:
        y = _y(tick)
        add(f'<line class="grid" x1="{LEFT}" y1="{y:.1f}" x2="{LEFT + PLOT_W}" '
            f'y2="{y:.1f}"/>')
        tick = round(tick + 0.1, 10)
    add('</g>')
    add('<g font-size="12" text-anchor="end">')
    tick = Y_MIN
    while tick <= Y_MAX + 1e-9:
        add(f'<text class="muted" x="{LEFT - 12}" y="{_y(tick) + 4:.1f}">{_fmt(tick)}</text>')
        tick = round(tick + 0.1, 10)
    add('</g>')

    # The pre-registered threshold. Dashed, because it is a commitment and not a measurement.
    ty = _y(threshold)
    add(f'<line class="threshold" x1="{LEFT}" y1="{ty:.1f}" x2="{LEFT + PLOT_W}" y2="{ty:.1f}" '
        f'stroke-width="1.5" stroke-dasharray="7 5"/>')
    add(f'<text class="muted" x="{LEFT + 4}" y="{ty - 9:.1f}" font-size="12" '
        f'text-anchor="start">pre-registered threshold {_fmt(threshold)}</text>')

    # The curve.
    coordinates = [(_x(i, len(points)), _y(p["fraction"])) for i, p in enumerate(points)]
    path = " ".join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}'
                    for i, (x, y) in enumerate(coordinates))
    add(f'<path d="{path}" fill="none" stroke="{ACCENT}" stroke-width="2.5" '
        f'stroke-linejoin="round"/>')

    for index, (point, (x, y)) in enumerate(zip(points, coordinates, strict=True)):
        add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{ACCENT}"/>')
        add(f'<text class="value" x="{x:.1f}" y="{y - 16:.1f}" font-size="16" font-weight="600" '
            f'text-anchor="middle">{point["fraction"]}</text>')
        denominator = f'{point["strong"]} of {point["denominator"]} flows'
        add(f'<text class="muted" x="{x:.1f}" y="{y + 26:.1f}" font-size="11" '
            f'text-anchor="middle">{denominator}</text>')

    # X axis: one tick per measurement, captioned with the blindness removed before it.
    axis_y = TOP + PLOT_H + 14
    add(f'<line class="axis" x1="{LEFT}" y1="{axis_y:.1f}" x2="{LEFT + PLOT_W}" '
        f'y2="{axis_y:.1f}" stroke-width="1"/>')
    for index, (point, (x, _)) in enumerate(zip(points, coordinates, strict=True)):
        add(f'<line class="axis" x1="{x:.1f}" y1="{axis_y:.1f}" x2="{x:.1f}" '
            f'y2="{axis_y + 6:.1f}" stroke-width="1"/>')
        add(f'<text x="{x:.1f}" y="{axis_y + 24:.1f}" font-size="12" '
            f'text-anchor="middle">measurement {index + 1}</text>')
        for line_index, line in enumerate(_wrap(captions[index])):
            add(f'<text class="muted" x="{x:.1f}" y="{axis_y + 41 + line_index * 14:.1f}" '
                f'font-size="11" text-anchor="middle">{_escape(line)}</text>')

    add(f'<text x="{LEFT}" y="24" font-size="17" font-weight="600">'
        f'Every repair to the instrument lowered the headline</text>')
    footer = ("Flows attributable to the tool call that caused them, number 5, measured three "
              "times in the order taken. The threshold was sealed before any measurement existed. "
              "Regenerate with make honesty-curve.")
    for line_index, line in enumerate(_wrap(footer, width=98)):
        add(f'<text class="muted" x="{LEFT}" y="{HEIGHT - 30 + line_index * 14:.1f}" '
            f'font-size="11">{_escape(line)}</text>')
    add('</svg>')
    return "\n".join(parts) + "\n"


def main() -> int:
    sys.stdout.write(render(curve_json()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
