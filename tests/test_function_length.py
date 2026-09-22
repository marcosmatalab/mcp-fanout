"""No function in the measurement core is longer than eighty lines.

Eighty, counted from `def` to the last line of the body, docstring included, and the number has an
argument behind it rather than a convention.

**Why a limit at all.** A function that does not fit on a screen is one a reader cannot hold while
checking it, and every function in this core computes a published figure. The limit is a number
rather than a judgement for the same reason every other threshold here is: "keep functions short"
is satisfied by whoever is reading it at the time.

**Why eighty and not sixty.** Sixty was tried first and measured: it flagged seventeen functions.
Seven of them were genuinely doing several things and were split, and the splits are in the code
(the grading pass that ran twice over the same flows, the sensor gate's four independent readings
of one graded list, the addon's attribution choice, the disclosure check's sorting and its
judging). The other ten were single figure assemblies, one `return {...}` carrying the reason for
each field beside it, where every available split moved the reason away from the field and made
the code worse. A limit that forces a worse structure is a limit set in the wrong place, so it was
moved to where the remaining failures would be real, which is exactly what fitting a threshold to
the data is NOT: nothing here is a measurement of the world, it is a style rule calibrated against
the codebase it governs, and it is stated so a reader can disagree with the number.

**Why the docstring counts.** A function whose docstring is thirty lines and whose body is fifty is
exactly as hard to hold as one with an eighty-line body, and the fix is the same either way: move
the argument into the module docstring or into a document. `match.grade_attribution` is the worked
example, at 100 lines of which 48 were an argument that `docs/DOCTRINE.md` already carries.

Scope: `src/mcpfanout` only. `tools/` produces one-shot figures and `tests/` are linear by nature,
and applying the limit there would generate churn with no reader on the other side of it.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / "src" / "mcpfanout"
LIMIT = 80

# Functions that were over the limit when it was introduced and are allowed to stay, each with the
# reason splitting it would make the code worse. An exemption is a decision, so it is written down
# with its argument; it is NOT a grandfather list that anything may be added to.
EXEMPT: dict[str, str] = {
    "cli.build_parser": (
        "one argparse declaration per subcommand, each two or three lines, in one place. Splitting "
        "it per command would scatter the CLI's surface across a dozen functions and make the "
        "whole surface unreadable in order to make each twelfth of it shorter"),
}


def _functions() -> list[tuple[str, str, int, int]]:
    """(module, qualified name, first line, length) for every function in the core."""
    out = []
    for path in sorted(CORE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            out.append((path.stem, f"{path.stem}.{node.name}", node.lineno, length))
    return out


def test_no_function_in_the_core_is_longer_than_the_limit():
    over = [(name, line, length) for _, name, line, length in _functions()
            if length > LIMIT and name not in EXEMPT]
    assert not over, (
        f"functions over {LIMIT} lines:\n  "
        + "\n  ".join(f"{name} at line {line}: {length} lines" for name, line, length in over)
        + f"\nSplit them, or add the name to EXEMPT in {Path(__file__).name} with the reason "
          "splitting it would make the code worse. An exemption is a decision, not a default.")


def test_every_exemption_is_still_needed():
    """An exemption that no longer applies is a rule with a hole in it."""
    lengths = {name: length for _, name, _, length in _functions()}
    stale = [name for name in EXEMPT if lengths.get(name, 0) <= LIMIT]
    assert not stale, (
        f"these are no longer over {LIMIT} lines and their exemptions should go: {stale}")
    missing = [name for name in EXEMPT if name not in lengths]
    assert not missing, f"EXEMPT names a function that no longer exists: {missing}"
