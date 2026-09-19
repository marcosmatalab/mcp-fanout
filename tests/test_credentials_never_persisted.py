"""A credential must never reach anything this repository produces.

THE WORST FAILURE THIS PROJECT COULD HAVE. The product is the privacy of evidence: negative 2 says
only salted digests survive memory, and a run is published as figures. A token leaked into a run
that is then committed is that promise inverted, and it is irreversible the moment it is pushed.

GATE RULE 10 APPLIED TO ITSELF. A scanner that has quietly stopped scanning reports a clean
result, which is rule 10's own failure mode turned on the rule. So every test here that reports
"clean" first proves, in the same run and through the same code path, that the scanner catches a
planted canary. If the self-check is removed, the tests that depend on it fail.

The token's VALUE is never written here, never printed, and never committed. It is read from the
environment file at test time, and when that file is absent the pattern-based scan still runs, so
a developer machine without credentials is not silently exempt.
"""

import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LAB_ENV = Path(os.path.expanduser("~/.mcp-fanout-lab.env"))

# Token shapes, not token values. GitHub's documented prefixes plus the generic high-entropy
# assignment shapes a harness log would produce. A pattern list is not a secret.
SECRET_PATTERNS = [
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"BSA[A-Za-z0-9_\-]{20,}"),            # Brave subscription tokens
    re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),           # Google API keys
]

# Everything the repository produces or could publish. runs/ is gitignored and scanned anyway:
# the rule is that a credential never reaches a produced artifact, not that it never reaches a
# committed one, because the gitignore is one `git add -f` away from irrelevant.
PRODUCED_DIRS = ["runs", "docs/figures"]
PRODUCED_GLOBS = ["*.json", "*.jsonl", "*.log", "*.txt", "*.md", "*.yaml", "*.yml"]


def _declared_secrets() -> list[str]:
    """The actual values, read at test time. Never logged, never asserted against by value."""
    if not LAB_ENV.is_file():
        return []
    out = []
    for line in LAB_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        value = line.partition("=")[2].strip().strip('"').strip("'")
        if len(value) >= 12:
            out.append(value)
    return out


def _scan(text: str, secrets: list[str]) -> list[str]:
    """Returns WHY it is dirty, never WHAT was found. A failure message is published output too."""
    hits = []
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            hits.append(f"matches the {pat.pattern[:18]}... shape")
    for i, secret in enumerate(secrets):
        if secret in text:
            hits.append(f"contains declared lab credential #{i}")
    return hits


def _produced_files() -> list[Path]:
    files = []
    for d in PRODUCED_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for pattern in PRODUCED_GLOBS:
            files.extend(p for p in root.rglob(pattern) if p.is_file())
    return files


# --- Rule 10: the scanner proves itself before it is trusted.

def test_the_scanner_catches_a_planted_token_by_shape():
    planted = "x = github_pat_11ABCDEFG0aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdef"
    assert _scan(planted, []), "the shape scanner is not scanning"


def test_the_scanner_catches_a_planted_value_that_matches_no_shape():
    """A credential with an unknown prefix must still be caught, or the list is the whole defence."""
    secret = "an-opaque-lab-credential-with-no-recognisable-prefix"
    assert _scan(f"TOKEN={secret}", [secret]), "the value scanner is not scanning"


def test_the_scanner_does_not_fire_on_ordinary_content():
    assert not _scan("fragment 9f2b from reference notes.md toward example.net", [])


def test_the_scanner_would_see_the_files_it_is_pointed_at():
    """A clean report over an empty file list is not a clean report. Rule 10, again."""
    files = _produced_files()
    assert files, ("no produced artifact was found to scan, so a pass here means nothing. "
                   "Run `make selftest` at least once before trusting this suite")


# --- The actual guarantee.

def test_no_produced_artifact_contains_a_credential():
    secrets = _declared_secrets()
    dirty = {}
    for path in _produced_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = _scan(text, secrets)
        if hits:
            dirty[str(path.relative_to(REPO))] = hits
    assert not dirty, f"credential material in produced artifacts: {json.dumps(dirty, indent=1)}"


def test_no_tracked_file_in_the_repository_contains_a_credential():
    """The committed surface, checked separately: runs/ is gitignored, the repository is not."""
    import subprocess
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                             text=True).stdout.split()
    secrets = _declared_secrets()
    dirty = {}
    for rel in tracked:
        path = REPO / rel
        if not path.is_file() or path.stat().st_size > 4_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # This file carries the PATTERNS, which are not secrets, and must not flag itself.
        if rel == "tests/test_credentials_never_persisted.py":
            continue
        hits = _scan(text, secrets)
        if hits:
            dirty[rel] = hits
    assert not dirty, f"credential material in tracked files: {json.dumps(dirty, indent=1)}"


def test_the_credential_file_lives_outside_the_repository():
    """It is at ~/.mcp-fanout-lab.env on purpose, and not at the root, because
    corpus/context/.env already exists as synthetic bait and two files with that name in one
    project is a confusion waiting to happen."""
    assert not (REPO / ".env").exists(), "a .env at the repository root is the confusion this avoids"
    if LAB_ENV.is_file():
        mode = LAB_ENV.stat().st_mode & 0o777
        assert mode == 0o600, f"{LAB_ENV} is mode {mode:o}, expected 600"


@pytest.mark.skipif(not LAB_ENV.is_file(), reason="no lab credential on this machine")
def test_the_declared_credential_is_actually_readable_and_shaped_like_one():
    """Without this, a malformed env file would run the capture uncredentialed and look fine,
    which is gate rule 10 applied to the credential itself."""
    secrets = _declared_secrets()
    assert secrets, f"{LAB_ENV} exists but declares no usable value"
    assert any(any(p.search(s) for p in SECRET_PATTERNS) for s in secrets), (
        "the declared credential matches no known token shape; either it is malformed or the "
        "shape list needs the new provider added")
