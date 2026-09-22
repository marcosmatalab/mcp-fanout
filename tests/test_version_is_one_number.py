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
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


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


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_each_version_is_a_plain_semver(name):
    """No pre-release suffixes. Editorial status belongs on a release title, not in a version.

    A suffix announces something provisional on its way to a version that does not exist. Semver
    alone already makes a later correction visible as `x.y.z+1`.
    """
    value = SOURCES[name]()
    assert SEMVER.match(value), f"{name} states {value!r}, which is not a bare MAJOR.MINOR.PATCH"


def test_the_importable_package_agrees_with_the_files():
    """Reading a file and importing the module are different things, and both are published."""
    import mcpfanout
    assert mcpfanout.__version__ == _pyproject()
