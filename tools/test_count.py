"""The test count the READMEs publish, measured by running the suite. Stdlib only.

WHY THIS EXISTS. The README published "691 passing" from a count of COLLECTED tests. On the machine
that wrote it the two numbers agreed, because that machine holds the lab credential one test needs;
on CI and in a clean clone that test is skipped, so the suite reports 690 passed and 1 skipped and
the badge was wrong for every reader. A figure about the suite has to come out of the suite.

WHAT IS PUBLISHED, AND WHY PASSED RATHER THAN COLLECTED. The published figure is the number of
tests that PASS in a clean environment: the one CI runs and a reader reproduces, with no lab
credential. Collected would count a test the reader's own run skips as passing, which is the claim
"passing" makes and the one that was false. The cost is that measuring it means running the whole
suite, about twenty seconds added to `make claims-check`, and that the figure depends on a stated
definition of "clean" instead of on a machine.

HOW "CLEAN" IS MADE, NOT ASSUMED. The suite runs in a subprocess whose HOME is a new, empty
temporary directory, so every per-user file the tests look for (today only the lab credential,
`~/.mcp-fanout-lab.env`) is absent by construction, on any machine. The alternative, an override
variable read by the credential test, would add a code path to the credential handling to serve a
documentation check; changing HOME touches nothing in the repository.

    python3 tools/test_count.py                              # prints the measurement as JSON
    python3 tools/test_count.py --check README.md README.es.md   # exits 1 if a README disagrees
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# pytest's final line, e.g. "690 passed, 1 skipped in 21.10s". Order of the parts varies.
SUMMARY_PART = re.compile(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)")
# Every place a README states the figure: the shields badge ("tests-690%20passing") and prose
# ("690 passing", "690 tests"). One pattern for both, so a new occurrence cannot be missed.
STATED = re.compile(r"\b(\d[\d,]*)(?:%20|\s|_)(?:tests|passing)\b")


def parse_summary(output: str) -> dict[str, int]:
    """Counts from the LAST pytest summary line in `output`. Raises if there is none."""
    lines = [line for line in output.splitlines() if SUMMARY_PART.search(line)
             and (" in " in line or line.strip().startswith("="))]
    if not lines:
        raise ValueError("no pytest summary line in the output; the suite did not report")
    counts: dict[str, int] = {}
    for number, kind in SUMMARY_PART.findall(lines[-1]):
        counts["errors" if kind.startswith("error") else kind] = int(number)
    return counts


def stated_counts(text: str) -> list[int]:
    return [int(m.replace(",", "")) for m in STATED.findall(text)]


def measure(repo: Path = REPO) -> dict:
    """Run the suite with an empty HOME and return what it reported."""
    with tempfile.TemporaryDirectory(prefix="mcpfanout-clean-home-") as home:
        env = dict(os.environ, HOME=home)
        env.pop("PYTEST_ADDOPTS", None)
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-p", "no:cacheprovider", "-o", "addopts="],
            cwd=repo, env=env, capture_output=True, text=True)
    counts = parse_summary(run.stdout)
    return {"passed": counts.get("passed", 0), "skipped": counts.get("skipped", 0),
            "failed": counts.get("failed", 0) + counts.get("errors", 0),
            "exit_code": run.returncode, "environment": "empty HOME: no lab credential",
            "command": "python3 tools/test_count.py"}


def check(readmes: list[Path], measured: dict) -> list[str]:
    """Every disagreement between what the READMEs state and what the suite reported."""
    problems = []
    if measured["exit_code"] != 0 or measured["failed"]:
        problems.append(f"the suite did not pass cleanly: {measured}")
    for path in readmes:
        stated = stated_counts(path.read_text(encoding="utf-8"))
        if not stated:
            problems.append(f"{path.name} states no test count")
        for value in stated:
            if value != measured["passed"]:
                problems.append(f"{path.name} says {value}, the suite passed {measured['passed']} "
                                f"({measured['skipped']} skipped) in a clean environment")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", nargs="+", type=Path, metavar="README",
                    help="fail if any of these files states a count other than the measured one")
    args = ap.parse_args(argv)
    measured = measure()
    print(json.dumps(measured, indent=2))
    if args.check:
        problems = check(args.check, measured)
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1 if problems else 0
    return 0 if measured["exit_code"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
