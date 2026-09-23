"""Both READMEs state the test count as a published figure. Keep the statement true automatically.

Rule 6 in this repository says no published figure without a command that measures it. The front
page publishes one ("N tests"), and a count restated by hand had gone stale at 23 while the suite
was at 128. Restating it by hand went wrong three times in a row, which is the argument for this
file rather than for more care.
"""

import re
from pathlib import Path

import pytest
from conftest import collected

REPO = Path(__file__).resolve().parent.parent
READMES = ("README.md", "README.es.md")
COUNT = re.compile(r"\b(\d[\d,]*)(?:%20|\s|_)(?:tests|passing)\b")


def _stated_counts(name: str) -> list[int]:
    text = (REPO / name).read_text(encoding="utf-8")
    return [int(m.replace(",", "")) for m in COUNT.findall(text)]


@pytest.mark.parametrize("name", READMES)
def test_the_readme_states_the_real_test_count(name: str):
    """Skipped unless the whole suite was collected, since a subset run has a different count."""
    count, modules = collected()
    on_disk = {p.name for p in (REPO / "tests").glob("test_*.py")}
    if modules != on_disk:
        pytest.skip(f"partial collection ({len(modules)} of {len(on_disk)} modules); "
                    "the stated count is only meaningful for the full suite")
    stated = _stated_counts(name)
    assert stated, f"{name} no longer states a test count; rule 6 wants the figure or nothing"
    for value in stated:
        assert value == count, (
            f"{name} says {value} tests, the suite collected {count}. "
            "Update every occurrence, or remove the figure.")


def test_the_detector_reads_a_planted_count():
    """Rule 10: a detector that has stopped matching would report every README as clean."""
    assert COUNT.findall("tests-688%20passing and 688 tests") == ["688", "688"]
