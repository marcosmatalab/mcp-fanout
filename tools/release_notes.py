"""Derive a release's notes from the SIGNED TAG, and verify that what was published is that text.

GATE RULE 10, NINTH INSTANCE, and the first one in a workflow rather than in code or in prose.
`.github/workflows/release.yml` published with `gh release create --notes-from-tag` under the
default `actions/checkout`, which clones at depth 1, and a comment two lines above the call
asserted the consequence: "the signed tag's own message is the notes, so the text that is signed
is the text that is published." Nothing in the job checked it. The text a release carries is not
derived from the tag by the file that claims it is; it is derived by a flag, from whatever the
runner's git happens to hold, and a ref whose annotated object was never fetched resolves to a
commit, whose message is then a plausible set of notes that nobody signed.

**What was measured, before this paragraph was written.** The first thing the `verify` command
below did was read the live `v1.0.0-rc1` release back from the API and compare: it MATCHES the
signed tag. So the claim was true and unverified, not false. That is the instance, not an excuse
for it: for the whole life of the release workflow nothing could have told a true claim from a
false one, and gate rule 10 is about which of those two a green result means. So this file
replaces the claim with two commands:

    python tools/release_notes.py write  <tag> <file>        # notes, derived explicitly
    python tools/release_notes.py verify <tag> <published>   # what GitHub actually shows

`write` REFUSES a tag it cannot read an annotation from, which is precisely the depth-1 case, so
the failure is loud at the step that would otherwise launder it. `verify` re-reads the published
body back from the release and fails if it is not the signed text, because a release is an
artifact and rule 10 says to check the value only a working instrument could produce rather than
the shape of the output. Verify, do not assert.

The signature itself is not checked here, for the reason tests/test_history_claims.py gives: a
runner holds no public key, and a check that fails for want of key material is a check everybody
learns to skip. What is checked is that the bytes published are the bytes the tag object carries.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class ReleaseNotesError(RuntimeError):
    """The tag cannot answer, or the published notes are not the tag's message."""


def _git(*args: str, repo: Path | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if out.returncode != 0:
        raise ReleaseNotesError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def _field(tag: str, field: str, repo: Path | None) -> str:
    # for-each-ref rather than `git tag -l --format`: it takes the full refname, so a branch and a
    # tag of the same name cannot be confused for each other.
    return _git("for-each-ref", f"refs/tags/{tag}", "--format", f"%({field})", repo=repo)


def tag_message(tag: str, repo: Path | None = None) -> str:
    """The annotated tag's subject and body, exactly as the tag object carries them.

    Raises rather than falling back. A lightweight tag, or an annotated tag whose object was never
    fetched, is indistinguishable here from a tag that was never pushed, and every one of those is
    a reason to stop the release instead of publishing somebody else's words as the tag's.
    """
    objecttype = _field(tag, "objecttype", repo).strip()
    if not objecttype:
        raise ReleaseNotesError(
            f"no ref refs/tags/{tag} in this checkout. A release's notes come from the tag object; "
            "fetch it (fetch-depth: 0 and fetch-tags: true) rather than letting the notes default "
            "to something else")
    if objecttype != "tag":
        raise ReleaseNotesError(
            f"refs/tags/{tag} is a {objecttype}, not an annotated tag object. Either the tag is "
            "lightweight and carries no message to sign, or the checkout fetched the ref without "
            "the object. Publishing here would silently use the COMMIT message as release notes")
    # The signature lives in contents:signature and is excluded from contents:body, so the text
    # assembled here is the signed message and nothing else.
    subject = _field(tag, "contents:subject", repo).strip("\n")
    body = _field(tag, "contents:body", repo).strip("\n")
    if not subject:
        raise ReleaseNotesError(f"refs/tags/{tag} is annotated but its message is empty")
    return f"{subject}\n\n{body}\n" if body else f"{subject}\n"


def _normalise(text: str) -> str:
    """Compare what a reader sees: trailing whitespace and CRLF are not a difference in notes."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def verify(published: str, expected: str) -> None:
    """Fail unless the published notes are the tag's message. No normalisation beyond whitespace."""
    if _normalise(published) == _normalise(expected):
        return
    got, want = _normalise(published), _normalise(expected)
    first = next((i for i, (a, b) in enumerate(zip(got.split("\n"), want.split("\n"),
                                                   strict=False)) if a != b), None)
    where = f"first differing line {first + 1}" if first is not None else "one is a prefix"
    raise ReleaseNotesError(
        "the published release notes are NOT the signed tag's message "
        f"({where}).\n--- published ---\n{got}\n--- tag ---\n{want}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="write the signed tag's message to a file, for --notes-file")
    w.add_argument("tag")
    w.add_argument("out", type=Path)
    v = sub.add_parser("verify", help="fail unless a published body is the signed tag's message")
    v.add_argument("tag")
    v.add_argument("published", type=Path, help="the body as the release API returns it")
    args = ap.parse_args(argv)
    try:
        expected = tag_message(args.tag)
        if args.cmd == "write":
            args.out.write_text(expected, encoding="utf-8")
            print(f"release notes for {args.tag} written to {args.out} "
                  f"({len(expected.splitlines())} lines, from the tag object)")
        else:
            verify(args.published.read_text(encoding="utf-8"), expected)
            print(f"published notes match the signed message of {args.tag}")
    except ReleaseNotesError as exc:
        print(f"release-notes: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
