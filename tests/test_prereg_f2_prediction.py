"""The F2 predictions and the INSTRUMENT verdict are pre-registered, which means frozen by digest.

Same mechanism and same reasoning as tests/test_phase_b_prediction.py: the whole block is hashed,
whitespace-normalised so reflowing to 100 columns is allowed and nothing else is. A prediction is
prose, so there is no cell to read and it could be rewritten after the run in a hundred small ways
that each look like an improvement.

If a prediction genuinely has to change, the digest below changes with it IN A SEPARATE COMMIT
that lands BEFORE the measurement, and the commit message says why.

WHAT IS DELIBERATELY NOT IN THE BLOCK. The product verdict. Of 127 flows in the run this work is
judged against, 108 are machinery and nine of ten servers ran without credentials (threats 5 and
8), so freezing a product decision against it would pre-register a conclusion about a measurement
that has not happened. Section 8 says so inside the block, which is the part that IS frozen: the
refusal to freeze is itself pre-registered, so it cannot be quietly replaced by a verdict later.

Frozen 2026-09-19, before any structural matcher existed.
"""

import hashlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PREREG = REPO / "docs" / "PREREG-F2.md"

BEGIN = "<!-- PREREGISTERED:BEGIN -->"
END = "<!-- PREREGISTERED:END -->"

PREREGISTERED_SHA256 = "51351087fb221cd1f9c403d59c2e021aea6d047b587ecd3eb0885be0d2bc58cb"


def _block() -> str:
    text = PREREG.read_text(encoding="utf-8")
    assert text.count(BEGIN) == 1 and text.count(END) == 1, "the markers are not unique"
    return text.split(BEGIN)[1].split(END)[0]


def _normalised() -> str:
    """Collapse all whitespace. Reflowing the prose is allowed; changing a word is not."""
    return " ".join(_block().split())


def test_the_prediction_block_is_unchanged_since_pre_registration():
    actual = hashlib.sha256(_normalised().encode()).hexdigest()
    assert actual == PREREGISTERED_SHA256, (
        "the pre-registered F2 block changed.\n"
        f"expected {PREREGISTERED_SHA256}\nfound    {actual}\n"
        "If this is a deliberate re-registration, it belongs in its own commit, landed BEFORE the "
        "measurement it predicts, with the reason in the message. If it is an edit made after "
        "seeing a result, it is the thing pre-registration exists to prevent.")


def test_every_piece_carries_a_falsification_condition():
    """A digest proves nothing changed. This proves the block still contains predictions.

    An emptied block with a matching digest is impossible, but a block rewritten BEFORE freezing
    into six paragraphs of hedging is not, and that is the failure this catches.
    """
    block = _block()
    for piece in ("P1", "P2", "P3", "P4", "P5", "P6"):
        assert re.search(rf"\*\*{piece},", block), f"{piece} is missing from the block"
    falsifiers = len(re.findall(r"[Ff]alsified", block))
    assert falsifiers >= 6, f"only {falsifiers} falsification conditions for six pieces"


def test_the_instrument_verdict_names_its_denominator_its_hash_and_its_threshold():
    """A threshold without the denominator it binds to is the defect this whole block exists for."""
    block = _block()
    assert "client-constant-paths.json" in block
    assert "6150f9c7" in block, "the frozen denominator list is not identified by digest"
    assert "Threshold: 0.80" in block
    assert "non-comparable" in block, "the raw fraction must be published and marked"


def test_the_refusal_to_freeze_a_product_verdict_is_itself_frozen():
    """So it cannot be replaced by a verdict after a result arrives, quietly."""
    block = _block()
    assert "Deliberately NOT frozen" in block
    for threat in ("Threat 5", "Threat 8"):
        assert threat in block, f"{threat} is not named as the reason"


def test_the_frozen_denominator_list_still_hashes_to_what_the_block_says():
    """The block quotes a sha256. If the file drifts, the quotation becomes a lie."""
    path = REPO / "registry" / "client-constant-paths.json"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual.startswith("6150f9c7"), (
        f"registry/client-constant-paths.json changed after it was frozen.\n"
        f"pre-registered prefix 6150f9c7, found {actual}.\n"
        "A change here moves the denominator of a pre-registered verdict. It belongs in a "
        "separate, labelled figure, not in this file.")
