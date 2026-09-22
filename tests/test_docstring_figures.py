"""The curve inside `shingle.py`'s module docstring must be the curve the sweep produces.

Gate 2's second half (`make claims-check`). The k sweep is quoted in four places: the artifact, the
calibration document, this docstring and the choice recorded in `calibrate.choose_k`. Three of them
had a test. The docstring did not, and it is the copy a reader meets first, because it sits beside
the constant it justifies.

It went stale exactly the way the document did: the negative corpus gained a fifth family, every
figure moved, and a docstring is invisible to a test suite that reads code but not prose. A comment
that justifies a constant with numbers the code no longer produces is worse than no comment, because
it reads as the record of a decision rather than as a memory of one.

The table is compressed on purpose (ranges, and "A down to B" for a column that falls across a
range) because an eighty-row table in a docstring is not read. The compression is what this file
has to understand, so each form is checked against every k it covers rather than against its
endpoints alone.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SHINGLE = REPO / "src" / "mcpfanout" / "shingle.py"
CURVE = REPO / "docs" / "figures" / "calibration" / "ksweep-calibration.json"

ROW = re.compile(r"^\s*(\d+)(?:-(\d+)|(\+))?\s+"        # k, or k-k, or k+
                 r"([\d.]+)\s+"                          # false positives
                 r"([\d.]+)\s+"                          # bench recall
                 r"([\d.]+)(?:\s+down to\s+([\d.]+))?\s*$")  # self-match, possibly a fall


def _curve() -> dict[int, dict]:
    data = json.loads(CURVE.read_text(encoding="utf-8"))
    return {row["k"]: row for row in data["curve"]}


def _docstring() -> str:
    text = SHINGLE.read_text(encoding="utf-8")
    return text.split('"""')[1]


def _table_rows() -> list[tuple[str, tuple]]:
    """The parsed rows, each with the raw line for a failure message that can be acted on."""
    rows = []
    started = False
    for line in _docstring().splitlines():
        if "false positives" in line and "bench recall" in line:
            started = True
            continue
        if not started:
            continue
        if not line.strip():
            if rows:
                break
            continue
        match = ROW.match(line)
        if not match:
            break
        rows.append((line.strip(), match.groups()))
    return rows


def test_the_docstring_still_carries_a_curve():
    rows = _table_rows()
    assert len(rows) >= 5, (
        "the k-sweep table in src/mcpfanout/shingle.py's docstring is gone or unparseable; it is "
        "the justification a reader meets beside the constant, and rule 6 wants it or nothing")


def _covered(groups) -> list[int]:
    k_lo = int(groups[0])
    if groups[1]:
        return list(range(k_lo, int(groups[1]) + 1))
    if groups[2]:
        return [k for k in _curve() if k >= k_lo]
    return [k_lo]


@pytest.mark.parametrize("raw,groups", _table_rows(), ids=lambda v: v if isinstance(v, str) else "")
def test_every_row_of_the_docstring_curve_matches_the_artifact(raw, groups):
    curve = _curve()
    _, _, _, fp, bench, self_first, self_last = groups
    ks = _covered(groups)
    assert ks, f"row covers no k in the swept range: {raw!r}"
    for k in ks:
        assert k in curve, f"row covers k = {k}, which the sweep does not measure: {raw!r}"
        row = curve[k]
        assert float(fp) == row["false_positives"]["rate"], (
            f"{raw!r}: at k = {k} the artifact's false-positive rate is "
            f"{row['false_positives']['rate']}, the docstring says {fp}")
        assert float(bench) == row["bench"]["recall"], (
            f"{raw!r}: at k = {k} the artifact's bench recall is {row['bench']['recall']}, "
            f"the docstring says {bench}")

    observed = [curve[k]["self_match"]["recall"] for k in ks]
    assert observed[0] == float(self_first), (
        f"{raw!r}: self-match at k = {ks[0]} is {observed[0]}, the docstring says {self_first}")
    if self_last is None:
        assert set(observed) == {float(self_first)}, (
            f"{raw!r}: self-match is not constant over k = {ks[0]}..{ks[-1]}, it is "
            f"{observed}; the row must say 'X down to Y'")
    else:
        assert observed[-1] == float(self_last), (
            f"{raw!r}: self-match at k = {ks[-1]} is {observed[-1]}, the docstring says "
            f"{self_last}")
        assert all(a >= b for a, b in itertools.pairwise(observed)), (
            f"{raw!r}: 'down to' claims a fall, and the artifact does not fall: {observed}")


def test_the_docstring_states_the_denominator_it_was_measured_over():
    """A rate without its denominator is the thing that went stale last time, silently."""
    data = json.loads(CURVE.read_text(encoding="utf-8"))
    pairs = data["curve"][0]["false_positives"]["pairs"]
    families = len(data["curve"][0]["false_positives"]["by_family"])
    text = " ".join(_docstring().split())
    assert f"{pairs} concurrent call pairs" in text, (
        f"the docstring does not say it was measured over {pairs} pairs")
    # Prose spells small counts out, and a test that forced digits would be tidying English
    # rather than checking a figure. Either form counts, no other number does.
    words = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    spellings = {str(families), words.get(families, str(families))}
    assert any(f"{spelling} families" in text for spelling in spellings), (
        f"the docstring does not say the corpus has {families} families")


def test_the_chosen_k_in_the_docstring_is_the_one_the_rule_picked():
    from mcpfanout.shingle import DEFAULT_K
    chosen = json.loads(CURVE.read_text(encoding="utf-8"))["choice"]["chosen_k"]
    assert chosen == DEFAULT_K, (
        f"the sweep picks k = {chosen} and the shipped constant is {DEFAULT_K}")
    text = " ".join(_docstring().split())
    assert f"default {DEFAULT_K}" in text, "the docstring no longer states the shipped k"
    assert f"That is {chosen}:" in text, (
        "the docstring no longer says which k the written rule picked")
