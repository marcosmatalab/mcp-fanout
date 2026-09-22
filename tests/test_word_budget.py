"""The documentation budget declared in docs/README.md must be the one the repository has.

Same class as tests/test_doc_references.py's size check, and for the same reason: a figure about
the documents is a published figure (rule 6), and the one place it will go stale is the one place
nobody re-measures. The difference is what it protects. A total word count can always be reached
by deleting evidence, so what is declared and gated here is the SPLIT: how much of the prose is
measured findings and how much is rules of operation and front matter.

Gate rule 10 applies to the classifier itself. The failure mode is not a wrong number, it is a
document nobody classified being counted anyway, silently, under whichever bucket a default
happened to pick. So the planted instance below is an unlisted path, put through the real entry
point, and the classifier must refuse it rather than absorb it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from word_budget import (  # noqa: E402
    CORPUS_MATERIAL,
    FINDINGS,
    OPERATION,
    SPLIT,
    UnclassifiedDocument,
    budget,
    classify,
    tracked_markdown,
)

INDEX = REPO / "docs" / "README.md"
TOLERANCE = 100          # the same rounding the docs index uses for each document's own size


def _declared() -> dict[str, int]:
    """The two figures docs/README.md publishes, read out of the sentence that publishes them."""
    text = " ".join(INDEX.read_text(encoding="utf-8").split())
    found = {}
    for bucket in ("findings", "operation"):
        m = re.search(rf"\*\*([\d,]+) words\*\* of {bucket}", text)
        assert m, (f"docs/README.md no longer declares the {bucket} figure in the words this test "
                   f"reads it from. Declare it, or delete this test in the same commit")
        found[bucket] = int(m.group(1).replace(",", ""))
    return found


def test_every_tracked_markdown_file_is_classified():
    """An unclassified document would make the published budget describe a different repository."""
    classify(tracked_markdown())              # raises if any tracked file is unlisted


def test_an_unlisted_document_is_REFUSED_rather_than_counted():
    """The planted instance: the classifier must go red when its input is not one it decided on.

    The path is assembled from pieces rather than written whole, because
    tests/test_doc_references.py scans every file in this repository for path-shaped literals and
    would report a planted one as a dangling reference.
    """
    planted = "docs/" + "a-document-nobody-classified" + ".md"
    with pytest.raises(UnclassifiedDocument) as exc:
        classify([planted])
    assert "not classified" in str(exc.value)


def test_no_document_is_in_two_buckets_at_once():
    overlap = (OPERATION & FINDINGS) | (OPERATION & CORPUS_MATERIAL) | (FINDINGS & CORPUS_MATERIAL)
    assert not overlap, f"classified twice, so counted twice: {sorted(overlap)}"
    assert not (set(SPLIT) & (OPERATION | FINDINGS | CORPUS_MATERIAL)), (
        "a split document must not also be filed whole")


def test_the_three_buckets_account_for_every_word():
    """Nothing may be hidden by being left out: the parts sum to the total, or the figure lies."""
    data = budget()
    assert (data["findings_words"] + data["operation_words"] + data["corpus_material_words"]
            == data["total_words"])
    assert data["documents"] == len(tracked_markdown())


def test_the_split_document_really_is_split():
    """If a heading moved, one side would collapse to zero and the budget would still look fine."""
    per_file = budget()["per_file"]
    for path in SPLIT:
        buckets = per_file[path]
        assert buckets.get("operation", 0) > 500, (
            f"{path}'s gate section measured {buckets.get('operation', 0)} words; the split is not "
            "finding the ten gate rules")
        assert buckets.get("findings", 0) > 500, (
            f"{path}'s measured-result sections collapsed to {buckets.get('findings', 0)} words")


def test_the_declared_budget_matches_the_measured_one():
    data, declared = budget(), _declared()
    problems = [f"docs/README.md says {declared[b]} {b} words, `make words` measures {actual}"
                for b, actual in (("findings", data["findings_words"]),
                                  ("operation", data["operation_words"]))
                if abs(declared[b] - actual) > TOLERANCE]
    assert not problems, "\n".join(problems) + (
        "\n\nRun `make words` and update the declaration, or explain the difference. The figure is "
        "published, so it is gated (rule 6).")


def test_the_index_names_the_command_behind_the_budget():
    text = INDEX.read_text(encoding="utf-8")
    assert "make words" in text, "a published figure needs its command beside it (rule 6)"
    assert "tools/word_budget.py" in text or "test_word_budget" in text, (
        "the index must say what re-derives and what gates the budget")
