"""The published test count is measured by tools/test_count.py; this file tests the measurer.

The README once stated "691 passing" from a count of COLLECTED tests, which agreed with the suite
only on the one machine holding the lab credential. The measurement now runs the suite itself,
with an empty HOME, inside `make claims-check`. It is not run from here: a test that launched the
whole suite would launch this file again. What is tested here is the part that can be wrong
silently, the parsing and the comparison, each with a planted instance (gate rule 10).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _tool():
    path = REPO / "tools" / "test_count.py"
    spec = importlib.util.spec_from_file_location("tool_test_count", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tc = _tool()
CLEAN = {"passed": 690, "skipped": 1, "failed": 0, "exit_code": 0}


def test_the_summary_line_is_parsed_whatever_the_order_of_its_parts():
    assert tc.parse_summary("....\n==== 690 passed, 1 skipped in 21.10s ====\n") == \
        {"passed": 690, "skipped": 1}
    assert tc.parse_summary("2 failed, 688 passed, 1 error in 3s") == \
        {"failed": 2, "passed": 688, "errors": 1}


def test_output_without_a_summary_is_refused_rather_than_read_as_zero():
    """A suite that crashed before reporting must not look like a suite that passed 0 of 0."""
    with pytest.raises(ValueError):
        tc.parse_summary("ImportError: no module named mcpfanout\n")


def test_every_way_the_readme_states_the_count_is_found():
    text = "[![tests](https://img.shields.io/badge/tests-690%20passing-2ea44f)] 690 passing tests"
    assert tc.stated_counts(text) == [690, 690]


def test_a_readme_that_disagrees_with_the_measurement_FAILS(tmp_path: Path):
    """The planted instance: the 691-against-690 case this file was written for."""
    readme = tmp_path / "README.md"
    readme.write_text("tests-691%20passing\n", encoding="utf-8")
    problems = tc.check([readme], CLEAN)
    assert problems and "says 691, the suite passed 690" in problems[0]


def test_a_readme_that_agrees_passes(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("tests-690%20passing and 690 passing tests\n", encoding="utf-8")
    assert tc.check([readme], CLEAN) == []


def test_a_readme_with_no_count_fails_rather_than_passing_vacuously(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("no figure here\n", encoding="utf-8")
    assert tc.check([readme], CLEAN) == [f"{readme.name} states no test count"]


def test_a_failing_suite_fails_the_check_even_if_the_numbers_agree(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("690 passing\n", encoding="utf-8")
    assert tc.check([readme], dict(CLEAN, failed=1, exit_code=1))


@pytest.mark.parametrize("name", ["README.md", "README.es.md"])
def test_both_readmes_are_checked_by_the_claims_gate(name: str):
    """The measurement is only a gate if the gate calls it on every README that states it."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    recipe = makefile.split("\nclaims-check:", 1)[1].split("\n\n", 1)[0]
    assert "tools/test_count.py --check" in recipe and name in recipe
