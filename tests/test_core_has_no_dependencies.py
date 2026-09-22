"""The measurement core imports the standard library and nothing else.

`pyproject.toml` declares `dependencies = []` and gives the reason: the core is what CI runs and
what `make verify` proves reproducible, so keeping it dependency-free removes a whole class of "the
number changed because a transitive dependency changed" failures, which is exactly the supply-chain
problem this project studies. That declaration was prose. Nothing checked it.

Two checks, because they fail differently:

- **Static.** Every module the core is declared to contain is parsed and every import in it is
  resolved against the standard library. This catches the import before it ships, in `make verify`,
  with no environment needed.
- **Runtime, in CI.** A separate job installs the package WITHOUT the `capture` extra and imports
  the core, so an import that only happens at call time, or a dependency that arrives through
  another dependency, fails there. The static check cannot see either.

The capture layer (`driver`, `capture_addon`) may use the `capture` extra, and `harness/`, `bench/`
and `tools/` are outside the core entirely. That split is the contract, and it is why every
registry file the core reads is JSON and not YAML: PyYAML would be a dependency of the thing that
computes the numbers.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CORE_DIR = REPO / "src" / "mcpfanout"

# The modules the contract covers, named here rather than globbed: a new module in the package is
# not automatically part of the core, and adding one to this list is the decision that makes it so.
CORE_MODULES = (
    "aggregate", "calibrate", "classify", "cli", "control", "demo", "disclosure", "match",
    "rarity", "record", "redact", "shingle", "structure", "bench_metrics",
)

# Modules that are NOT in the core, with what they are allowed to need.
CAPTURE_LAYER = {"driver", "capture_addon"}

# Third-party names that must never appear in a core import, listed so the failure message can
# name the dependency rather than say "something".
FORBIDDEN = ("mitmproxy", "yaml", "requests", "numpy", "pandas", "scipy", "matplotlib",
             "pydantic", "httpx", "aiohttp")


def _imports(path: Path) -> set[str]:
    """Top-level module names imported by a file, at any nesting depth, absolute imports only."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _is_stdlib(name: str) -> bool:
    if name in sys.stdlib_module_names:
        return True
    return name in {"mcpfanout"}


@pytest.mark.parametrize("module", CORE_MODULES)
def test_a_core_module_imports_only_the_standard_library(module):
    path = CORE_DIR / f"{module}.py"
    assert path.is_file(), (
        f"{module} is declared part of the core and does not exist. Either the module was renamed "
        "and CORE_MODULES was not, or the contract now covers nothing")
    outside = sorted(n for n in _imports(path) if not _is_stdlib(n))
    assert not outside, (
        f"src/mcpfanout/{module}.py imports {outside}, which is outside the standard library.\n"
        "pyproject.toml declares the measurement core dependency-free, and the reason is in the "
        "comment above that declaration: the core is what CI runs and what the reproducibility "
        "claim rests on. If this import belongs to the capture layer, the code that needs it "
        "belongs there too.")


def test_the_capture_layer_is_the_only_place_a_dependency_may_live():
    """The split is the contract. A core module that grew a capture import is what this catches."""
    for name in CAPTURE_LAYER:
        assert name not in CORE_MODULES, (
            f"{name} is in both the core list and the capture layer; the contract cannot say both")
    for module in CORE_MODULES:
        text = (CORE_DIR / f"{module}.py").read_text(encoding="utf-8")
        for dependency in FORBIDDEN:
            assert f"import {dependency}" not in text, (
                f"src/mcpfanout/{module}.py mentions `import {dependency}`, including inside a "
                "function. A deferred import is still a dependency: it fails at call time, in the "
                "path that computes a number, which is worse than failing at import time")


def test_the_declaration_in_pyproject_still_says_what_this_file_enforces():
    """A test enforcing a contract nobody declares any more is a test enforcing a habit."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies = []" in text, (
        "pyproject.toml no longer declares the core dependency-free. If that was deliberate, this "
        "file and the CI job beside it are the things to delete, in the same commit, with the "
        "reason")
    assert "capture = [" in text, "the capture extra is gone, so the layer split has no other side"


def test_every_core_module_is_importable_without_the_capture_extra_installed():
    """The static check cannot see a dependency that arrives through another dependency.

    This is the weak version of the CI job: it proves the modules import in THIS environment,
    which has the capture extra available, so it cannot prove the absence of a dependency. The
    strong version is the `core-isolation` job in .github/workflows/ci.yml, which installs without
    the extra and fails if any of these imports reaches for something that is not there.
    """
    import importlib

    for module in CORE_MODULES:
        importlib.import_module(f"mcpfanout.{module}")
