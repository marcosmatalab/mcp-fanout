"""The phase B predictions are pre-registered, which means frozen by digest before the data exists.

Why a digest and not a presence check. The sensor gate's thresholds are pre-registered too, and
`tests/test_doc_references.py` protects them by reading the specific cells that define them, because
the first version of that test looked for a word anywhere in the document and a softened threshold
passed. A prediction is worse than a threshold in this respect: it is prose, so there is no cell to
read, and it could be rewritten after the run in a hundred small ways that each look like an
improvement. So the whole block is hashed, whitespace-normalised so reflowing to 100 columns is
allowed and nothing else is.

If a prediction genuinely has to change, the digest below changes with it IN A SEPARATE COMMIT that
lands BEFORE the run, and the commit message says why. That is a visible act in the history rather
than an edit nobody can date afterwards, which is the entire value of pre-registration. Changing
both in the same commit as a result is exactly the move this file exists to make impossible to do
quietly.

Measured 2026-09-19, before any concurrent phase B run existed.
"""

import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# The sealed block moved into docs/PROTOCOL.md when the three governance documents were
# merged. Moving it is safe exactly because of the digest below: the block travelled byte
# for byte and this test is what proves it did.
PHASES = REPO / "docs" / "PROTOCOL.md"

BEGIN = "<!-- PREREGISTERED:BEGIN -->"
END = "<!-- PREREGISTERED:END -->"

# sha256 of the whitespace-normalised block between the markers. Frozen 2026-09-19, before the run.
PREREGISTERED_SHA256 = "82ed06048be67c6589dbe52a32b20cbea0f352ac64ecc49eb51c223fdcdf519f"


def _block() -> str:
    text = PHASES.read_text()
    assert text.count(BEGIN) == 1 and text.count(END) == 1, "the markers are not unique"
    return text.split(BEGIN)[1].split(END)[0]


def _normalised() -> str:
    """Collapse all whitespace. Reflowing the prose is allowed; changing a word is not."""
    return " ".join(_block().split())


def test_the_prediction_block_is_unchanged_since_pre_registration():
    actual = hashlib.sha256(_normalised().encode()).hexdigest()
    assert actual == PREREGISTERED_SHA256, (
        "the pre-registered prediction block changed.\n"
        f"expected {PREREGISTERED_SHA256}\nfound    {actual}\n"
        "If this is a deliberate re-registration, it belongs in its own commit, landed BEFORE the "
        "run it predicts, with the reason in the message. If it is an edit made after seeing a "
        "result, it is the thing pre-registration exists to prevent.")


def test_both_predictions_are_present_and_say_what_they_claim():
    """The digest proves nothing changed; this proves the block still contains predictions.

    A block replaced wholesale would fail the digest test, but an empty block with a matching digest
    is impossible only as long as something checks that the content is a prediction at all. These are
    the load-bearing claims, not a spell check.
    """
    block = _normalised()
    assert "**B1." in block and "**B2." in block
    # B1: direction (worse than the bench) and failure mode (ambiguity, not a false claim).
    assert "WORSE than on the bench" in block
    assert "`CONTENT_AMBIGUOUS` rather than a false attribution" in block
    # The measurable form has to be a formula, not an adjective.
    assert "CONTENT_UNIQUE / (CONTENT_UNIQUE + CONTENT_AMBIGUOUS)" in block
    # B2: the denominator claim, so a thin top of the distribution is not read as B1 confirmed.
    assert "UNATTRIBUTED" in block
    for i, claim in enumerate(("What falsifies B1", "What falsifies B2")):
        assert claim in block, claim


def test_the_unfalsifiable_half_is_labelled_as_such():
    """Whether a strong claim made in phase B was CORRECT cannot be checked in phase B.

    Precision needs a known cause, which exists only on the bench (gate rule 8). A prediction whose
    second half cannot be tested in the pass that motivates it must say so where it is written, or
    the run will be read as having confirmed something it cannot observe.
    """
    block = _normalised()
    assert "CANNOT falsify the second half" in block
    assert "no ground truth" in block
    assert "Phase C" in block


def test_the_observed_section_comes_after_the_prediction_and_is_outside_it():
    """Results are written below the frozen block, never into it."""
    text = PHASES.read_text()
    assert "### Observed, concurrent pass" in text
    assert text.index(END) < text.index("### Observed, concurrent pass")
    assert "Observed" not in _block()


def test_the_prediction_block_quotes_no_result():
    """A figure inside the block would mean a result was written into the prediction.

    Two exemptions, both pre-existing facts rather than outcomes: the bench's measured ratio of 1.0
    (phase A, already published) and the ladder's levels. Anything else numeric in the block is a
    result that arrived after the prediction was written.
    """
    block = _normalised()
    allowed = {"1.0", "16", "2", "5", "10", "3"}
    found = set(re.findall(r"\b\d+(?:\.\d+)?\b", block))
    unexplained = found - allowed
    assert not unexplained, f"numbers in the prediction block that are not the bench's or the ladder's: {sorted(unexplained)}"
