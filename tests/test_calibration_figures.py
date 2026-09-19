"""The calibration figures are committed, and the prose that quotes them cannot drift from them.

Same arrangement as the run aggregates under docs/figures/ (tests/test_committed_figures.py), for
the same reason: gate rule 6 wants a command behind every published figure, and a figure quoted in a
document is only re-derivable if the artifact it came from is in the repository. The difference is
that these are fully re-derivable by anyone, because the corpus they are measured over IS committed:
`make fp` reproduces the file byte for byte on any machine, with no Docker and no network.

So these tests check three things: the artifact says what it was measured at, the prose quotes it
verbatim, and the reserved half is not being published in a form that could be confused with the
calibration half.
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CALIB_FIGURES = REPO / "docs" / "figures" / "calibration"
DOC = REPO / "docs" / "CALIBRATION.md"


def _artifacts() -> list[Path]:
    return sorted(CALIB_FIGURES.glob("fp-*.json"))


def test_a_published_false_positive_figure_is_committed():
    """Gate rule 9 turns on this number, so it has to be re-derivable from the repository."""
    published = [p for p in _artifacts() if "held-out" in p.name]
    assert published, "no held-out false-positive figure committed; run `make fp`"


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_figure_carries_the_parameters_that_make_it_comparable(path):
    """A rate quoted without k and without the weighting state is not a rate, it is a rumour."""
    d = json.loads(path.read_text())
    assert d["k"] >= 1
    assert d["half"] in ("calibration", "held_out")
    assert d["pairs"] >= 200, "the acceptance criterion was at least 200 pairs"
    assert d["command"].startswith("make fp")
    assert d["name"] == "matcher_false_positive_rate_on_structured_language"
    # The filename has to agree with the contents, or two incomparable figures can overwrite
    # each other's conclusions while both look current.
    assert f"k{d['k']}" in path.name
    assert d["half"].replace("_", "-") in path.name
    assert ("weighted" if d.get("rarity_weighting") else "unweighted") in path.name


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_figure_is_byte_stable(path):
    d = json.loads(path.read_text())
    assert path.read_text() == json.dumps(d, indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_pooled_figure_is_the_sum_of_its_families(path):
    d = json.loads(path.read_text())
    assert d["pairs"] == sum(f["pairs"] for f in d["by_family"].values())
    assert d["false_positives"] == sum(f["false_positives"] for f in d["by_family"].values())
    lo, hi = d["wilson_95"]
    assert lo <= d["rate"] <= hi


def _published() -> dict:
    return json.loads((CALIB_FIGURES / "fp-held-out-k16-unweighted.json").read_text())


def test_the_document_quotes_the_artifact_and_not_a_remembered_number():
    """Every figure in the F1.1 section is rebuilt from the artifact and required verbatim.

    Rebuilt rather than spot-checked: the first version of the equivalent test for threat 10 only
    asserted that one number appeared somewhere in the section, so softening a different occurrence
    of it passed. Here the pooled sentence and every family row are reconstructed from the file.
    """
    d = _published()
    text = " ".join(DOC.read_text().split())

    headline = (f"**Held-out half, k = {d['k']}, no weighting: {d['false_positives']} false "
                f"positives in {d['pairs']} pairs, a rate of {d['rate']}, Wilson 95% interval "
                f"[{d['wilson_95'][0]}, {d['wilson_95'][1]}].**")
    assert headline in text, f"the document does not state the measured result: {headline!r}"

    for family, f in d["by_family"].items():
        row = (f"| `{family}` | {f['pairs']} | {f['false_positives']} | {f['rate']} | "
               f"[{f['wilson_95'][0]}, {f['wilson_95'][1]}] |")
        assert row in text, f"row for {family} does not match the artifact: {row!r}"


def test_the_document_states_the_pair_count_the_acceptance_criterion_asked_for():
    text = " ".join(DOC.read_text().split())
    assert f"**{_published()['pairs']} ordered pairs per half**" in text


def test_the_document_names_the_command_and_the_artifact():
    text = DOC.read_text()
    assert "make fp" in text and "fp-held-out-k16-unweighted.json" in text


def test_the_document_carries_its_own_threats():
    """A measurement that does not say how it could be wrong is not a measurement (gate rule 6)."""
    text = DOC.read_text()
    section = text.split("## Threats to this measurement")[1]
    numbered = re.findall(r"^\d+\. \*\*", section, flags=re.MULTILINE)
    assert len(numbered) >= 4, f"only {len(numbered)} threats stated"
    assert "hand-authored" in section
    assert "model of a server" in section


def test_the_document_keeps_the_two_pending_pieces_marked_pending():
    """F1.2 and F1.3 are unmeasured until they are measured; a doc that reads finished invites a quote."""
    text = DOC.read_text()
    for heading in ("## F1.2", "## F1.3"):
        block = text.split(heading)[1].split("\n## ")[0]
        if "Pending" not in block:
            # Once a piece lands, its section must carry a measured figure and its command instead.
            assert "make " in block, f"{heading} is neither pending nor backed by a command"


def test_no_calibration_figure_leaks_corpus_content():
    """The figures are counts. A false positive is interesting; the string that caused it is data.

    The negative corpus is synthetic and committed, so nothing here is sensitive, but the habit is
    the point: an artifact that quoted the colliding fragment would be the one place in this
    repository where published output carries payload bytes.
    """
    import json as _json
    for path in _artifacts():
        text = path.read_text()
        for half_file in ("calibration.json", "held-out.json"):
            data = _json.loads((REPO / "corpus" / "negative" / half_file).read_text())
            for fam in data["families"]:
                for call in fam["calls"]:
                    for item in call["information"]:
                        assert item not in text, f"{path.name} quotes corpus content: {item!r}"
