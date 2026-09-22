"""No document may name a pre-release as the current one. That pointer goes stale on the next tag.

The same class as every other stale pointer this repository has caught: a sentence that was true
when it was written, that nothing re-reads, and that keeps being served to a reader long after the
thing it names has been superseded. `README.md` and `CONTRIBUTING.md` both named a specific
release candidate as the tagged and citable artifact, so the next tag would have made both of them
wrong with nothing to notice, on the front page.

The fix is not a better sentence, it is not having one: the README carries the release badge and
both documents link to `/releases/latest`, which GitHub resolves at read time. This file is what
keeps it that way.

**Naming a pre-release is allowed where it is a dated record rather than a pointer.** Gate rule
10's ninth instance in `docs/PROTOCOL.md` names the release whose notes were wrong, with the
timestamps, because an instance nobody can look up is an anecdote. The allowlist below is that
distinction, written down: history may name a tag, current state may not.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# v1.2.3-something. The final-release form (v1.0.0) is deliberately NOT matched: naming the
# version a commitment is made about is a statement with a date attached, not a pointer at
# whatever happens to be newest.
PRERELEASE = re.compile(r"\bv\d+\.\d+\.\d+-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*")
# The identifier may not END in a dot: "v9.9.9-rc7." at the end of a sentence is the tag
# v9.9.9-rc7, and a detector that reported the full stop as part of the name would print a
# string nobody can grep for.

SCANNED_SUFFIXES = {".md", ".cff", ".yml", ".yaml", ".toml", ".py"}

# May name a pre-release, because each records something that happened at a stated time.
HISTORICAL = {
    "docs/PROTOCOL.md",            # gate rule 10, ninth instance, with the API timestamps
    "tools/release_notes.py",      # the same failure, written where the fix lives
}


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return [line for line in out.stdout.splitlines() if line]


def stale_pointers(paths: list[str]) -> dict[str, list[str]]:
    """path -> the pre-release names it puts in front of a reader as current."""
    found: dict[str, list[str]] = {}
    for path in paths:
        if path in HISTORICAL or path.startswith("tests/"):
            continue
        if Path(path).suffix not in SCANNED_SUFFIXES:
            continue
        hits = PRERELEASE.findall((REPO / path).read_text(encoding="utf-8", errors="replace"))
        if hits:
            found[path] = sorted(set(hits))
    return found


def test_no_document_names_a_pre_release_as_the_current_one():
    found = stale_pointers(_tracked())
    assert not found, (
        "these name a pre-release, which is a pointer that goes stale on the next tag:\n"
        + "\n".join(f"  {path}: {', '.join(hits)}" for path, hits in found.items())
        + "\n\nLink to /releases/latest, or take the figure from a command. If the mention is a "
          "dated historical record, add the file to HISTORICAL here and say why.")


def test_the_detector_finds_a_planted_pointer(tmp_path: Path, monkeypatch):
    """Rule 10 turned on this file: a scanner that has stopped scanning reports a clean result."""
    # The path is assembled from pieces because tests/test_doc_references.py scans every file
    # here for path-shaped literals and would report a planted one as a dangling reference.
    name = "docs/" + "planted" + ".md"
    (tmp_path / "docs").mkdir()
    (tmp_path / name).write_text("The citable artifact is the tag v9.9.9-rc7.\n")
    monkeypatch.setattr("test_no_stale_release_pointer.REPO", tmp_path)
    assert stale_pointers([name]) == {name: ["v9.9.9-rc7"]}


def test_a_final_version_is_not_flagged(tmp_path: Path, monkeypatch):
    """v1.0.0 is a commitment with a date, not a pointer, and flagging it would train people off."""
    name = "docs/" + "planted" + ".md"
    (tmp_path / "docs").mkdir()
    (tmp_path / name).write_text("v1.0.0 is reserved for 19 October 2026.\n")
    monkeypatch.setattr("test_no_stale_release_pointer.REPO", tmp_path)
    assert stale_pointers([name]) == {}


@pytest.mark.parametrize("name", ["README.md", "CONTRIBUTING.md"])
def test_the_documents_point_at_the_link_that_resolves_itself(name: str):
    text = (REPO / name).read_text(encoding="utf-8")
    assert "releases/latest" in text, (
        f"{name} must send the reader to /releases/latest, which GitHub resolves when it is read, "
        "rather than to a tag name that was current when this was written")
