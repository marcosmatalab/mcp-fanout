"""A claim about the commit history is a published figure, and this checks it against the history.

`CITATION.cff` says the argument depends on the signed commit history, so three documents state
where signing begins. One of them named the wrong commit, off by one, and the commit it named is
the one the pre-registration's timeline table cites as external evidence. Nobody had checked it
because there was nothing to check it with: every other figure in this repository has a command
behind it (rule 6) and this class of claim did not.

**Presence, not validity.** The test asserts that a commit object carries a `gpgsig` header, which
is checkable anywhere, by anyone, with no key material. Whether a signature VERIFIES depends on
having the public key, which a CI runner and a stranger's clone do not have, and a test that fails
for want of a key would be a test everyone learns to ignore. Verification is a reader's job and
`git log --show-signature` is the command for it; what this file guarantees is that the boundary
the documents state is the boundary the objects have.

Skipped, loudly, on a shallow clone: `actions/checkout` defaults to depth 1, and a history of one
commit would let every assertion here pass while checking nothing, which is gate rule 10's failure
mode applied to this file. The CI job fetches the full history so the skip does not happen there.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CONTRIBUTING = REPO / "CONTRIBUTING.md"


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, f"git {' '.join(args)}: {out.stderr.strip()}"
    return out.stdout.strip()


def _is_shallow() -> bool:
    return _git("rev-parse", "--is-shallow-repository") == "true"


def _has_signature(sha: str) -> bool:
    """Does this commit object carry a signature header? No key material required."""
    header = _git("cat-file", "commit", sha).split("\n\n", 1)[0]
    return any(line.startswith(("gpgsig", "gpgsig-sha256")) for line in header.splitlines())


def _declared_boundary() -> str:
    """The commit the documents say signing begins at, read from CONTRIBUTING.md."""
    match = re.search(r"signed with\s+GPG,\s+from\s+`([0-9a-f]{7,40})`\s+onward",
                      " ".join(CONTRIBUTING.read_text(encoding="utf-8").split()))
    assert match, ("CONTRIBUTING.md no longer states where signing begins. Either say it, with the "
                   "commit, or delete this test in the same commit that deletes the claim")
    return match.group(1)


@pytest.fixture(autouse=True)
def _needs_a_full_history():
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    if _is_shallow():
        pytest.skip("shallow clone: the history is not here to check, and passing would be worse")


def test_every_commit_from_the_declared_boundary_onward_is_signed():
    boundary = _declared_boundary()
    shas = _git("rev-list", f"{boundary}^..HEAD").splitlines()
    assert shas, f"{boundary} is not in this history"
    unsigned = [sha[:7] for sha in shas if not _has_signature(sha)]
    assert not unsigned, (
        f"CONTRIBUTING.md says every commit from {boundary} onward is signed, and these are not: "
        f"{unsigned}. Sign them, or move the boundary and say why.")


def test_the_boundary_is_the_FIRST_signed_commit_and_not_a_later_one():
    """Off by one is the way this claim was wrong, so it is the way the test looks at it."""
    boundary = _declared_boundary()
    parent = _git("rev-parse", f"{boundary}^")
    assert not _has_signature(parent), (
        f"{parent[:7]}, the commit BEFORE the declared boundary, is also signed. The boundary is "
        "later than it needs to be, which understates the history: move it back.")


def test_the_documents_agree_with_each_other_about_the_boundary():
    """Three files state it. A claim stated three times is a claim wrong in two of them."""
    boundary = _declared_boundary()
    for name in ("README.md", "docs/PREREG-F2.md"):
        text = " ".join((REPO / name).read_text(encoding="utf-8").split())
        assert boundary in text, (
            f"{name} does not name {boundary} as the commit signing begins at, and "
            "CONTRIBUTING.md does")


def test_the_unsigned_prefix_is_named_rather_than_left_to_be_discovered():
    """A history that is partly signed and described as signed is the overclaim to avoid."""
    boundary = _declared_boundary()
    before = len(_git("rev-list", f"{boundary}^").splitlines())
    if before == 0:
        return                                  # the whole history is signed; nothing to disclose
    readme = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
    assert "not re-signed" in readme or "deliberately not" in readme, (
        f"{before} commits before {boundary} carry no signature and the README does not say so. "
        "Say it: back-signing a history replaces real provenance with manufactured provenance, "
        "and that is the reason, not an excuse")
