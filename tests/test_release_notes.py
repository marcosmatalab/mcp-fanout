"""Gate rule 10 for the release notes: the depth-1 failure must go red, not fall back quietly.

The defect this guards is in the repository's history: `release.yml` published with
`--notes-from-tag` under a checkout of depth 1, which does not fetch the annotated tag object, so
the notes silently became the COMMIT message while a comment in the same file asserted that the
signed tag's message was what got published.

So the planted instance is exactly that condition, built in a temporary repository: a lightweight
tag, which is what a ref without its object looks like to every command that reads a message from
it. A detector that returned the commit message there would be the bug, and one that returned an
empty string would be worse, because empty notes read as a tag whose author wrote none.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from release_notes import ReleaseNotesError, main, tag_message, verify

SUBJECT = "Measurement complete, disclosure window open until 2026-10-19"
BODY = "The instrument did NOT meet its pre-registered threshold: 0.6579 against 0.80.\n\nSecond."
COMMIT_MESSAGE = "Bump the version and regenerate the figures"


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with one commit, one annotated tag and one lightweight tag.

    Signing is off here on purpose: this file checks that the published bytes are the tag's bytes,
    which is checkable with no key material, for the reason tests/test_history_claims.py gives.
    """
    _git(tmp_path, "init", "-q", "-b", "main")
    for key, value in (("user.name", "t"), ("user.email", "t@example.invalid"),
                       ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        _git(tmp_path, "config", key, value)
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-q", "-m", COMMIT_MESSAGE)
    _git(tmp_path, "tag", "-a", "v9.9.9", "-m", f"{SUBJECT}\n\n{BODY}")
    _git(tmp_path, "tag", "v9.9.9-light")
    return tmp_path


def test_the_notes_are_the_annotated_tags_own_subject_and_body(repo: Path):
    notes = tag_message("v9.9.9", repo=repo)
    assert notes.splitlines()[0] == SUBJECT
    assert BODY in notes
    assert COMMIT_MESSAGE not in notes, "the commit message leaked into the release notes"


def test_a_tag_without_its_object_FAILS_instead_of_falling_back_to_the_commit(repo: Path):
    """The planted instance: this is what depth 1 leaves behind, and it must stop the release."""
    with pytest.raises(ReleaseNotesError) as exc:
        tag_message("v9.9.9-light", repo=repo)
    assert "lightweight" in str(exc.value)
    assert COMMIT_MESSAGE not in str(exc.value)


def test_a_tag_that_is_not_here_at_all_fails(repo: Path):
    with pytest.raises(ReleaseNotesError) as exc:
        tag_message("v0.0.0-absent", repo=repo)
    assert "fetch" in str(exc.value)


def test_verification_rejects_the_commit_message_published_as_notes(repo: Path):
    """The exact shape of the defect: a well-formed release whose notes nobody signed."""
    with pytest.raises(ReleaseNotesError) as exc:
        verify(COMMIT_MESSAGE, tag_message("v9.9.9", repo=repo))
    assert "NOT the signed tag's message" in str(exc.value)


def test_verification_rejects_an_edited_body_and_says_where(repo: Path):
    expected = tag_message("v9.9.9", repo=repo)
    with pytest.raises(ReleaseNotesError) as exc:
        verify(expected.replace("0.6579", "0.8947"), expected)
    assert "first differing line" in str(exc.value)


def test_verification_accepts_the_published_text_through_crlf_and_trailing_space(repo: Path):
    expected = tag_message("v9.9.9", repo=repo)
    verify(expected.replace("\n", "  \r\n") + "\n\n", expected)


def test_the_cli_writes_a_notes_file_and_verifies_it(repo: Path, tmp_path: Path, monkeypatch,
                                                     capsys):
    monkeypatch.chdir(repo)
    out = tmp_path / "notes.md"
    assert main(["write", "v9.9.9", str(out)]) == 0
    assert SUBJECT in out.read_text()
    assert main(["verify", "v9.9.9", str(out)]) == 0
    out.write_text(COMMIT_MESSAGE)
    assert main(["verify", "v9.9.9", str(out)]) == 1
    assert "NOT the signed tag" in capsys.readouterr().err


def test_the_cli_exits_non_zero_on_the_depth_one_tag(repo: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(repo)
    assert main(["write", "v9.9.9-light", str(tmp_path / "notes.md")]) == 1
