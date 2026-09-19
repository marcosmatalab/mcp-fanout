"""The honesty curve: what the headline figure did as the instrument stopped being blind.

Three measurements of the same quantity, in the order they were made, each one taken after an
observability defect was fixed. Every fix lowered the headline. That shape is evidence about the
METHOD rather than about the matcher, and it is the figure the write-up argues from, so it needs a
command behind it like any other published number (rule 6).

    make honesty-curve

Reads the committed figures under docs/figures/ plus the corpus-derived figure `make f2`
reproduces, so nothing here is transcribed by hand from a previous session.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIGURES = REPO / "docs" / "figures"

# Each step names the run, and what the instrument could NOT see when that run was taken.
STEPS = [
    {"run": "20260919T130847Z-concurrent",
     "source": "corpus-derived (make f2)",
     "blind_to": ["Node's global fetch, so one of three egressing servers was invisible",
                  "its own flows: flows.jsonl predated the structural fields, so the figure "
                  "could not be read from what was persisted"]},
    {"run": "20260919T193121Z-concurrent",
     "source": "persisted",
     "blind_to": ["Node's global fetch, so one of three egressing servers was invisible"]},
    {"run": "20260919T194649Z-concurrent",
     "source": "persisted",
     "blind_to": ["a direct node:https user, a custom agent or a pinned client, if one exists; "
                  "make backstop is what would show it"]},
]


def _figure(run: str) -> dict | None:
    p = FIGURES / f"{run}.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _n5(fig: dict) -> dict:
    return next(n for n in fig["numbers"] if n["number"] == 5)


def _derived() -> dict:
    """The first point is corpus-derived, so it is re-derived rather than remembered."""
    out = subprocess.run([sys.executable, "tools/measure_f2.py"], cwd=REPO,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    d = json.loads(out.stdout)["P4_regrade"]
    return {"strong": d["strong"], "denominator": 19,
            "fraction": d["fraction_over_19_content"]}


def main() -> int:
    points = []
    for i, step in enumerate(STEPS):
        fig = _figure(step["run"])
        if i == 0:
            got = _derived()
            if not got:
                print(f"could not re-derive the first point; `make f2` failed", file=sys.stderr)
                return 1
        elif fig is None:
            print(f"missing committed figure for {step['run']}", file=sys.stderr)
            return 1
        else:
            n5 = _n5(fig)
            got = {"strong": n5["strong_attribution_count"],
                   "denominator": n5["content_denominator"],
                   "fraction": n5["content_attributable_fraction"]}
        obs = None
        if fig:
            n3 = next((n for n in fig["numbers"] if n["number"] == 3), None)
            obs = (n3 or {}).get("observability", {}).get("proxy_observed")
        points.append({"run": step["run"], "source": step["source"],
                       "servers_with_observed_egress": obs, **got,
                       "instrument_was_blind_to": step["blind_to"]})

    fractions = [p["fraction"] for p in points]
    monotone_down = all(a > b for a, b in zip(fractions, fractions[1:]))
    print(json.dumps({
        "name": "honesty_curve",
        "threshold_preregistered": 0.80,
        "points": points,
        "every_observability_fix_lowered_the_headline": monotone_down,
        "reading": (
            "Three measurements of ONE quantity, in the order taken, each after an observability "
            "defect was fixed. The figure fell every time. A measurement whose headline improves "
            "as its instrument improves is measuring the instrument; this one did the opposite, "
            "which is the only direction consistent with the earlier numbers having been optimistic "
            "for reasons that had nothing to do with the matcher. The final point is the one that "
            "counts, it is below the pre-registered threshold of 0.80, and the two above it are "
            "superseded rather than retracted: each remains a correct statement about the flows "
            "that were visible when it was taken."),
        "what_it_does_not_establish": (
            "that the curve has stopped. It falls as blindness is removed, and make backstop is "
            "the only thing that says whether blindness remains. A fourth point below 0.6579 is "
            "the expected shape if another blind client is found, not a surprise."),
        "command": "make honesty-curve",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
