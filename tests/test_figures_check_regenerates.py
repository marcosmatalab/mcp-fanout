"""`figures-check` must REGENERATE every figure it checks, including the one whose exit it ignores.

GATE RULE 10, TENTH INSTANCE. The target's whole reason to exist is that a test which INSPECTS a
committed figure passes just as happily when the figure is eight commits stale, so it recomputes
each one and fails on a non-empty `git diff`. One line did not do that. `rarity` exits 1 by design,
so its invocation carried make's leading `-`, and `-` ignores EVERY non-zero exit rather than the
documented one: a `rarity` that raised left the committed JSON untouched, the diff came out clean,
and the gate went green over a figure nobody had recomputed. Measured, not argued: with a
`RuntimeError` planted in `rarity.acceptance`, the old recipe exited 0 and the current one exits 2.

The fix is to delete the artifact before the step that rewrites it, so "did not regenerate" and
"was deleted" are the same observable and the `git diff --exit-code` already in the target catches
it. This file keeps that pairing: an ignored exit code with no delete in front of it is the defect
returning, whatever the target it is added to.

What this file does NOT do is run `make figures-check`, which takes most of a minute. It reads the
recipe, which is where the invariant lives; the two red/green runs behind the paragraph above were
done by hand, once, the way gate rule 10 asks.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAKEFILE = REPO / "Makefile"
RECIPE_PREFIX = ">"          # set by .RECIPEPREFIX at the top of the Makefile


def recipe(target: str, text: str | None = None) -> list[str]:
    """The recipe lines of one target, without the prefix. Comments and blanks are not lines."""
    text = MAKEFILE.read_text(encoding="utf-8") if text is None else text
    lines: list[str] = []
    seen = False
    for line in text.splitlines():
        if re.match(rf"^{re.escape(target)}\s*:", line):
            seen = True
            continue
        if not seen:
            continue
        if line.startswith(RECIPE_PREFIX):
            lines.append(line[len(RECIPE_PREFIX):].strip())
        elif line.startswith("#") or not line.strip():
            continue                       # a make comment inside a recipe is not a recipe line
        else:
            break                          # the next target begins
    assert seen, f"no target {target!r} in the Makefile"
    return lines


def unpaired_ignored_steps(lines: list[str]) -> list[str]:
    """Steps whose exit code is ignored with no `rm` before them, so failure leaves no trace."""
    removed_something = False
    out = []
    for line in lines:
        if line.startswith("rm "):
            removed_something = True
        elif line.startswith("-") and not removed_something:
            out.append(line)
    return out


def test_figures_check_deletes_before_the_step_whose_exit_it_ignores():
    lines = recipe("figures-check")
    ignored = [line for line in lines if line.startswith("-")]
    assert ignored, ("figures-check no longer ignores any exit code. If that is deliberate, delete "
                     "this test in the same commit; if a step was dropped, put it back")
    assert not unpaired_ignored_steps(lines), (
        "an ignored exit code with no `rm` in front of it:\n  "
        + "\n  ".join(unpaired_ignored_steps(lines))
        + "\n\n`-` ignores EVERY non-zero exit, not only the documented one, so a crash leaves the "
          "committed figure untouched and the diff clean. Delete the artifact first.")


def test_the_rarity_artifact_named_for_deletion_is_the_one_rarity_writes():
    """A glob that matches nothing deletes nothing, and the gate is back to inspecting."""
    removals = [line for line in recipe("figures-check") if line.startswith("rm ")]
    assert removals, "figures-check deletes nothing before regenerating"
    globs = [part for line in removals for part in line.split()[2:]]
    matched = [p for g in globs for p in REPO.glob(g)]
    assert matched, f"none of {globs} matches a committed figure; the deletion is a no-op"
    for path in matched:
        assert path.exists() and path.suffix == ".json", path


def test_the_target_still_ends_by_comparing_and_by_refusing_untracked_figures():
    """The delete is only safe because these two run after it. Losing either hides a deletion."""
    lines = recipe("figures-check")
    assert any(line.startswith("git diff --exit-code docs/figures/") for line in lines), (
        "figures-check must end by diffing docs/figures/; the deletion above is caught by it")
    assert any("ls-files --others" in line for line in lines), (
        "an untracked figure is a published number nobody can re-derive")


def test_the_detector_finds_a_planted_unpaired_step():
    """Rule 10 turned on this file: a rule that has stopped being checked reports compliance."""
    planted = ["$(MAKE) fp", "-$(MAKE) rarity", "git diff --exit-code docs/figures/"]
    assert unpaired_ignored_steps(planted) == ["-$(MAKE) rarity"]
    # The path is assembled from pieces because tests/test_doc_references.py scans every file here
    # for path-shaped literals and would report a planted one as a dangling reference.
    removal = "rm -f " + "docs/figures/" + "planted.json"
    assert unpaired_ignored_steps([removal, *planted[1:]]) == []
