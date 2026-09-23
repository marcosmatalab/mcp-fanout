"""Measure the repository's prose budget: how much of it is findings and how much is government.

WHY THIS EXISTS. Chasing a total word count is the wrong target, because the cheapest way to hit
one is to delete evidence: threats, pre-registrations and calibration notes are the longest
documents here and the most expensive to lose. A DECLARED and GATED split is worth more than a
reached total, so this file measures the split and `tests/test_word_budget.py` fails when the
figure declared in `docs/README.md` stops matching it. Rule 6, applied to the documentation's own
size: a number in a document needs a command behind it, including a number ABOUT the documents.

THE TWO BUCKETS, and the line between them.

  findings   what was measured, predicted, disclosed or captured, plus the method and the corpora
             the numbers are read through. Cutting here costs evidence. This is the bucket that is
             allowed to grow.
  operation  how to work in this repository and how it presents itself: the four negatives, the
             ten gate rules, the contributor and security notes, the index, and the front page.
             Cutting here costs nothing but repetition, which is why the overlap between the
             operating notes, DOCTRINE.md and PROTOCOL.md was removed rather than trimmed evenly.

Two documents are mixed and are split by section rather than being filed whole, because filing
either one whole would move about two thousand words to the wrong side of the line:

  docs/PROTOCOL.md   part 1 is the ten gate rules (operation); parts 2 and 3 are the phases, the
                     sensor gate's measured result and the stop gate that fired (findings).

A third bucket, `corpus_material`, holds markdown files that are measurement INPUT rather than
prose about it: a synthetic bait document is not a finding and is not a rule. It is reported
rather than dropped, and the three buckets must sum to the total, so nothing can be hidden by
being unclassified.

    make words
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Classification is a LIST, not a pattern. A glob would silently absorb a new document into
# whichever bucket its directory happens to suggest, and the whole point of the figure is that
# somebody decided which side of the line each document is on. An unlisted file is an error.
OPERATION = {
    "README.md",                  # the front page
    "README.es.md",               # the front page, in Spanish
    "CONTRIBUTING.md",            # how to run the gates
    "SECURITY.md",                # how a finding about someone else's project is handled
    "docs/README.md",             # the index, and this budget's declaration
    "docs/DOCTRINE.md",           # the four negatives: the single source
}
FINDINGS = {
    "docs/METHOD.md",
    "docs/THREATS.md",
    "docs/PREREG-F2.md",
    "docs/CALIBRATION.md",
    "docs/DISCLOSURE-LOG.md",
    "docs/disclosure/2026-09-19-puppeteer-docs-gap.md",
    "docs/disclosure/2026-09-19-readabilipy-npm-install-at-call-time.md",
    "runs/README.md",
    "corpus/concurrent/README.md",
    "corpus/background/README.md",
    "corpus/context/README.md",
}
CORPUS_MATERIAL = {
    "corpus/context/customer_note.md",     # synthetic bait, carrying a CANARY_ token. Not prose.
}
# path -> (heading that starts the operation part, heading that ends it). Everything outside the
# span is findings. Both headings are asserted by tests/test_doc_references.py, so neither can be
# renamed without a test going red first.
SPLIT = {
    "docs/PROTOCOL.md": ("## Part 1: the gate", "## Part 2: the three phases"),
}


class UnclassifiedDocument(RuntimeError):
    """A markdown file nobody decided about. Counting it either way would be a guess."""


def tracked_markdown(repo: Path = REPO) -> list[str]:
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return sorted(line for line in out.stdout.splitlines() if line)


def _words(text: str) -> int:
    """The same count `wc -w` and tests/test_doc_references.py use, so three figures agree."""
    return len(text.split())


def classify(paths: list[str], repo: Path = REPO) -> dict[str, dict[str, int]]:
    """path -> {bucket: words}. Raises on anything not decided about above."""
    out: dict[str, dict[str, int]] = {}
    for path in paths:
        # Classified BEFORE the file is opened, so an unlisted path fails as unclassified rather
        # than as a missing file: the refusal has to be about the decision, not about the disk.
        if path not in SPLIT and path not in OPERATION and path not in FINDINGS \
                and path not in CORPUS_MATERIAL:
            raise UnclassifiedDocument(
                f"{path} is not classified in tools/word_budget.py. Decide whether it is a "
                "finding, a rule of operation, or corpus material, and say so there: an "
                "unclassified document would make the published budget describe a different set "
                "of files than the repository has")
        text = (repo / path).read_text(encoding="utf-8")
        if path in SPLIT:
            start, end = SPLIT[path]
            if start not in text or end not in text:
                raise UnclassifiedDocument(
                    f"{path} is split at {start!r}..{end!r} and one of those headings is gone. "
                    "Re-decide the split rather than letting the words land in one bucket")
            head, rest = text.split(start, 1)
            gate, tail = rest.split(end, 1)
            out[path] = {"operation": _words(start) + _words(gate),
                         "findings": _words(head) + _words(end) + _words(tail)}
        elif path in OPERATION:
            out[path] = {"operation": _words(text)}
        elif path in FINDINGS:
            out[path] = {"findings": _words(text)}
        else:
            out[path] = {"corpus_material": _words(text)}
    return out


def budget(repo: Path = REPO) -> dict:
    per_file = classify(tracked_markdown(repo), repo)
    totals = {"findings": 0, "operation": 0, "corpus_material": 0}
    for buckets in per_file.values():
        for bucket, words in buckets.items():
            totals[bucket] += words
    total = sum(totals.values())
    return {
        "name": "documentation_word_budget",
        "command": "make words",
        "declared_in": "docs/README.md",
        "total_words": total,
        "findings_words": totals["findings"],
        "operation_words": totals["operation"],
        "corpus_material_words": totals["corpus_material"],
        "findings_share": round(totals["findings"] / total, 4) if total else 0.0,
        "documents": len(per_file),
        "per_file": {path: dict(sorted(b.items())) for path, b in sorted(per_file.items())},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--summary", action="store_true",
                    help="two lines instead of JSON: the pair of figures docs/README.md declares")
    args = ap.parse_args(argv)
    try:
        data = budget()
    except UnclassifiedDocument as exc:
        print(f"word-budget: {exc}", file=sys.stderr)
        return 1
    if args.summary:
        print(f"findings   {data['findings_words']:>6} words  "
              f"({data['findings_share']:.1%} of {data['total_words']})")
        print(f"operation  {data['operation_words']:>6} words  "
              f"(plus {data['corpus_material_words']} words of corpus material)")
    else:
        print(json.dumps(data, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
