"""Every artifact in this repository must state the same version, or none of them means anything.

GATE RULE 10, SIXTH INSTANCE. `pyproject.toml` and `mcpfanout.__version__` said 0.1.0 while
`CITATION.cff` said 1.0.0, in the same commit, with nothing able to notice. That is the class
exactly: two artifacts of one repository asserting different facts, each well-formed, each
passing every check that existed.

It matters more here than in most projects. The citation metadata is what a reader uses to name
what they read, and this paper's whole argument is about provenance. A repository that cannot keep
its own version straight is not in a position to publish a claim about tying effects to causes.

The version is parsed with the standard library rather than with a YAML or TOML dependency,
because the measurement core is standard-library only and a test that drags in a parser to check
a one-line field is a dependency bought for nothing.
"""

import re
import subprocess
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _pyproject() -> str:
    for line in (REPO / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"\s*$', line.strip())
        if m:
            return m.group(1)
    pytest.fail("pyproject.toml declares no version")


def _package() -> str:
    init = (REPO / "src" / "mcpfanout" / "__init__.py").read_text(encoding="utf-8")
    for line in init.splitlines():
        m = re.match(r'^__version__\s*=\s*"([^"]+)"\s*$', line.strip())
        if m:
            return m.group(1)
    pytest.fail("mcpfanout/__init__.py declares no __version__")


def _citation() -> str:
    """The `version:` key, not `cff-version:`, which is the schema's version and not ours."""
    for line in (REPO / "CITATION.cff").read_text(encoding="utf-8").splitlines():
        m = re.match(r'^version:\s*"?([^"\s]+)"?\s*$', line)
        if m:
            return m.group(1)
    pytest.fail("CITATION.cff declares no version")


def _compose_image_tag() -> str:
    for line in (REPO / "harness" / "docker-compose.yml").read_text(encoding="utf-8").splitlines():
        m = re.search(r"image:\s*mcp-fanout-harness:(\S+)", line)
        if m:
            return m.group(1)
    pytest.fail("docker-compose.yml declares no harness image tag")


SOURCES = {
    "pyproject.toml": _pyproject,
    "mcpfanout.__version__": _package,
    "CITATION.cff": _citation,
    "harness image tag": _compose_image_tag,
}


def test_every_artifact_states_the_same_version():
    """The one this file exists for. A divergence is a defect, not a formatting difference."""
    found = {name: fn() for name, fn in SOURCES.items()}
    assert len(set(found.values())) == 1, (
        "artifacts of this repository disagree about its version:\n"
        + "\n".join(f"  {k}: {v}" for k, v in found.items())
        + "\nThis is gate rule 10: each file is well-formed and they contradict each other.")


# PEP 440, because pyproject.toml is read by pip: MAJOR.MINOR.PATCH, optionally rcN.
PEP440 = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?$")
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$")
# The final release is a written commitment with a date (CONTRIBUTING.md: the disclosure window
# closes on 19 October 2026). Before it, the version may not claim the final.
FINAL_NOT_BEFORE = date(2026, 10, 19)


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_each_version_is_a_final_or_a_release_candidate(name):
    """What replaced the plain-semver rule. That rule forbade a pre-release suffix on the grounds
    that editorial status belongs on a release title, and its consequence was a package declaring
    1.0.0 while the latest release was v1.0.0-rc2 and the final was weeks away: every artifact
    agreed with every other and all of them were ahead of what had been released. A candidate
    number is not editorial status, it is the name of the thing a reader installs."""
    value = SOURCES[name]()
    assert PEP440.match(value), f"{name} states {value!r}, not MAJOR.MINOR.PATCH[rcN] (PEP 440)"


def _tags() -> list[tuple[int, int, int, float]]:
    out = subprocess.run(["git", "tag", "--list", "v*"], cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout: there are no tags to compare the version with")
    found = [TAG.match(line.strip()) for line in out.stdout.splitlines()]
    # A final sorts after all of its candidates, so its rc slot is infinity.
    return sorted((int(m[1]), int(m[2]), int(m[3]), float(m[4]) if m[4] else float("inf"))
                  for m in found if m)


def allowed_versions(latest: tuple[int, int, int, float], today: date) -> set[str]:
    """The latest release itself, the next candidate after it, and the final of that candidate's
    line once its date has come. Anything else is a version nobody released or will release next."""
    major, minor, patch, rc = latest
    base = f"{major}.{minor}.{patch}"
    if rc == float("inf"):
        return {base, f"{major}.{minor}.{patch + 1}rc1"}
    allowed = {f"{base}rc{int(rc)}", f"{base}rc{int(rc) + 1}"}
    if today >= FINAL_NOT_BEFORE:
        allowed.add(base)
    return allowed


def test_the_version_is_the_latest_release_or_the_next_candidate():
    """The defect this was written for: 1.0.0 declared while the latest tag was v1.0.0-rc2."""
    tags = _tags()
    if not tags:
        pytest.skip("no release tags in this checkout (CI fetches them with fetch-depth 0)")
    latest = tags[-1]
    allowed = allowed_versions(latest, date.today())
    found = {name: fn() for name, fn in SOURCES.items()}
    wrong = {name: v for name, v in found.items() if v not in allowed}
    assert not wrong, (f"the latest tag is {latest}; the version may only be one of "
                       f"{sorted(allowed)}, and these are not: {wrong}")


def test_the_rule_refuses_the_version_that_was_published_ahead_of_its_release():
    """Planted, so the rule is checked independently of whatever the tags happen to be today."""
    rc2 = (1, 0, 0, 2.0)
    assert "1.0.0" not in allowed_versions(rc2, date(2026, 9, 23))
    assert "1.0.0rc3" in allowed_versions(rc2, date(2026, 9, 23))
    assert "1.0.0rc4" not in allowed_versions(rc2, date(2026, 9, 23))
    assert "1.0.0" in allowed_versions((1, 0, 0, 3.0), FINAL_NOT_BEFORE)


def test_the_importable_package_agrees_with_the_files():
    """Reading a file and importing the module are different things, and both are published."""
    import mcpfanout
    assert mcpfanout.__version__ == _pyproject()
