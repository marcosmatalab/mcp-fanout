"""The bench must not share a mechanism with the instrument it measures.

THIS IS THE TEST THAT MAKES RECALL AND PRECISION MEAN ANYTHING. The bench emits the ground truth
and the harness emits the measurement; if the bench learned which tool call it was serving from
anything the harness also uses, then comparing "did the sensor attribute correctly?" against
"what does the bench say?" would compare the sensor to a copy of itself. The precision figure
would be partly circular and worth nothing, and it would LOOK fine.

The bench learns the call the only legitimate way: the call arrived on its own stdin, over MCP
stdio, addressed to it. Everything below exists to keep that the only way.

Checked against the import graph and the source, not against a convention: a rule that depends on
remembering it is not a property.
"""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BENCH = REPO / "bench"
# The harness-side driver is allowed to use the harness: it IS the harness. Everything else under
# bench/ is the pattern generator and must stand alone.
HARNESS_SIDE = {"drive_bench.py"}


def _bench_modules() -> list[Path]:
    return sorted(p for p in BENCH.glob("*.py") if p.name not in HARNESS_SIDE)


def _code_strings(path: Path) -> set[str]:
    """Every string literal the CODE uses, excluding docstrings.

    Docstrings are excluded because they are prose, and the prose in bench/server.py explains
    precisely which harness mechanisms it must not touch. A check that forbade naming the
    prohibition would push the explanation out of the file, which is the opposite of what the
    rule is for.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings}


def _imported_names(path: Path) -> set[str]:
    """Every module name imported anywhere in the file, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            # A relative import inside bench/ cannot reach mcpfanout, but record it anyway so a
            # future package layout cannot smuggle one in.
            if node.level:
                names.add("." * node.level + (node.module or ""))
    return names


def test_the_bench_directory_exists_and_has_the_pattern_generator():
    assert _bench_modules(), "bench/ has no standalone modules; the bench is the pattern generator"
    assert (BENCH / "server.py").is_file()
    assert (BENCH / "sink.py").is_file()


@pytest.mark.parametrize("path", _bench_modules(), ids=lambda p: p.name)
def test_the_bench_imports_nothing_from_the_harness(path):
    """Not just capture_addon: nothing from mcpfanout at all, which is the strong form.

    Forbidding only the addon would leave match.py, redact.py and driver.py reachable, and any of
    those would let the bench compute its truth with the same code the sensor uses. Banning the
    whole package makes the isolation checkable in one line instead of being a judgement call
    about which module is safe.
    """
    offenders = {n for n in _imported_names(path) if n == "mcpfanout" or n.startswith("mcpfanout.")}
    assert not offenders, f"{path.name} imports from the harness: {sorted(offenders)}"


@pytest.mark.parametrize("path", _bench_modules(), ids=lambda p: p.name)
def test_the_bench_never_reads_the_harness_control_directory(path):
    """active_calls.json is the harness telling the addon what is in flight.

    If the bench read it, it would be deriving its ground truth from the instrument's own
    bookkeeping, and the attribution it reported would already contain the sensor's answer.
    """
    used = _code_strings(path)
    for forbidden in ("MCPFANOUT_CONTROL", "active_calls.json", "current_call.json"):
        assert not any(forbidden in u for u in used), (
            f"{path.name} uses {forbidden} in code, not merely in prose explaining the rule")


@pytest.mark.parametrize("path", _bench_modules(), ids=lambda p: p.name)
def test_the_bench_reads_no_harness_environment_variable(path):
    """The harness configures the addon through MCPFANOUT_*. The bench must ignore all of it."""
    leaked = sorted(u for u in _code_strings(path) if u.startswith("MCPFANOUT"))
    assert not leaked, f"{path.name} reads harness configuration: {leaked}"


def test_the_bench_writes_its_truth_from_its_own_handler():
    """The ledger has to be written where the call is known natively, not reconstructed later.

    A ledger assembled after the fact, from anything other than the handler that served the call,
    would be a second guess rather than ground truth.
    """
    src = (BENCH / "server.py").read_text()
    tree = ast.parse(src)
    writers = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_truth"]
    assert writers, "bench/server.py has no ledger writer"
    # And the ledger path comes from the bench's own variable, not from harness configuration.
    assert "BENCH_TRUTH" in src


def test_the_harness_never_reads_the_truth_ledger():
    """The addon must not see the answer sheet. Only the comparator opens it, after the fact.

    Isolation has to hold in both directions. A sensor that could read the ledger would be able
    to agree with it for free, which is the same circularity from the other side.
    """
    addon = REPO / "src" / "mcpfanout" / "capture_addon.py"
    used = _code_strings(addon)
    assert not any("BENCH_TRUTH" in u or "truth" in u.lower() for u in used), (
        "the capture addon references the bench truth ledger")
    imported = _imported_names(addon)
    assert not any(n.startswith("bench") for n in imported), (
        "the capture addon imports from the bench")
