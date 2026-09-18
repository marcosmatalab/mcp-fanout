"""CLAUDE.md states the test count as a hard rule. Keep the statement true automatically.

Rule 6 in this repository says no published figure without a command that measures it. CLAUDE.md
publishes a figure ("Currently N tests") inside a hard rule, and it had gone stale at 23 while the
suite was at 128. Restating it by hand went wrong three times in a row, which is the argument for
this file rather than for more care.
"""

import re
from pathlib import Path

import pytest

from conftest import collected

REPO = Path(__file__).resolve().parent.parent
CLAUDE = REPO / "CLAUDE.md"


def _stated_counts() -> list[int]:
    text = CLAUDE.read_text()
    return [int(m) for m in re.findall(r"Currently (\d+)\s*\n?\s*tests", text)] + \
           [int(m) for m in re.findall(r"make verify\s+# (\d+) tests", text)]


def test_claude_md_states_the_real_test_count():
    """Skipped unless the whole suite was collected, since a subset run has a different count."""
    count, modules = collected()
    on_disk = {p.name for p in (REPO / "tests").glob("test_*.py")}
    if modules != on_disk:
        pytest.skip(f"partial collection ({len(modules)} of {len(on_disk)} modules); "
                    "the stated count is only meaningful for the full suite")

    stated = _stated_counts()
    assert stated, "CLAUDE.md no longer states a test count; rule 6 wants the figure or nothing"
    for value in stated:
        assert value == count, (
            f"CLAUDE.md says {value} tests, the suite collected {count}. "
            "Update every occurrence in CLAUDE.md, or remove the figure.")


def test_the_count_is_stated_in_both_places_that_quote_it():
    """The hard rule and the run instructions both carry it, and both must be right."""
    assert len(_stated_counts()) == 2, (
        "expected the count in exactly two places in CLAUDE.md: the hard rule and the "
        "`make verify` comment")
