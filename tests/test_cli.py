"""The command line, exercised through its real entry point.

Rule 6 says every published number has a command behind it, which makes `cli.py` the surface every
figure in this repository is actually produced through. It was the least covered module in the
core, at 35%, and the parts nobody exercised were the ones that decide what gets written where: the
run resolver, the refusals, and the artifact writers.

These tests call `cli.main(argv)` rather than importing the function behind a subcommand. A test
that calls the function directly proves the function works and proves nothing about whether the
argument that reaches it is the one the flag names, which is the defect class gate rule 10 is
about: `make n1` read whatever ran last because nothing checked the resolver.

Everything here runs offline, against the committed example runs and tmp_path. The two subcommands
that need Docker and network (`run`, and `control-compare` against a live control) are not
exercised, and their absence is named here rather than left to be inferred from the coverage
number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcpfanout import cli

REPO = Path(__file__).resolve().parent.parent


def _run(capsys, *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


# --- aggregate, the command behind every one of the six -----------------------------------------

@pytest.mark.parametrize("number", ["1", "2", "3", "4", "5", "6", "all"])
def test_aggregate_computes_each_number_from_the_committed_example_run(capsys, number):
    code, out = _run(capsys, "aggregate", "--run", "example-concurrent", "--number", number)
    assert code == 0
    data = json.loads(out)
    if number == "all":
        assert [n["number"] for n in data["numbers"]] == [1, 2, 3, 4, 5, 6]
    else:
        assert data["number"] == int(number)
        assert data["command"] == f"make n{number}"


def test_aggregate_resolves_a_bare_run_name_under_runs(capsys):
    """`RUN=example-concurrent` is how the README and the Makefile refer to a run."""
    code, out = _run(capsys, "aggregate", "--run", "example-concurrent", "--number", "5")
    assert code == 0
    assert json.loads(out)["content_attributable_fraction"] == 0.6579


def test_aggregate_refuses_a_directory_that_is_not_a_run(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["aggregate", "--run", str(tmp_path), "--number", "1"])
    assert "not a run directory" in str(exc.value)


def test_aggregate_refuses_a_pass_nobody_drove(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    with pytest.raises(SystemExit) as exc:
        cli.main(["aggregate", "--run", "latest-sequential", "--number", "1"])
    assert "no completed" in str(exc.value)


# --- selftest and figures, the two commands that WRITE ------------------------------------------

def test_selftest_builds_a_run_and_computes_its_numbers(capsys, tmp_path):
    code, out = _run(capsys, "selftest", "--out", str(tmp_path / "selftest"))
    assert code == 0
    for name in ("manifest.json", "calls.jsonl", "flows.jsonl"):
        assert (tmp_path / "selftest" / name).is_file()
    assert "numbers" in out


def test_figures_writes_a_normalized_aggregate_that_names_nothing(capsys, tmp_path):
    code, _ = _run(capsys, "figures", "--run", "example-sequential", "--out", str(tmp_path))
    assert code == 0
    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    text = written[0].read_text(encoding="utf-8")
    assert '"normalized": true' in text
    for forbidden in ("npmjs", "github", "api.", "third-party-a"):
        assert forbidden not in text, f"the published aggregate names {forbidden}"


def test_figures_labels_a_run_with_no_pass_as_unlabelled(capsys, tmp_path):
    """A grade distribution whose driving condition is unknown must SAY so in the artifact.

    Not a refusal: runs predating the two-pass split are committed and their figures are readable
    as what they are. What may not happen is an artifact that omits the condition, because a
    figure read as the wrong pass is the error the split exists to prevent.
    """
    from mcpfanout.record import RunManifest, write_jsonl, write_manifest

    run = tmp_path / "unlabelled"
    write_manifest(run / "manifest.json", RunManifest(
        run_id="unlabelled", created="1970-01-01T00:00:00Z", salt_fixed=True, k=22, w=8,
        corpus_sha256="0" * 64))
    write_jsonl(run / "calls.jsonl", [])
    write_jsonl(run / "flows.jsonl", [])
    code, _ = _run(capsys, "figures", "--run", str(run), "--out", str(tmp_path / "out"))
    assert code == 0
    written = json.loads((tmp_path / "out" / "unlabelled.json").read_text(encoding="utf-8"))
    assert written["provenance"]["pass"] == "unlabelled"


# --- the calibration commands, which are where a half can be pointed at the wrong thing ----------

def test_calibrate_publishes_the_held_out_half(capsys, tmp_path):
    code, out = _run(capsys, "calibrate", "--half", "held_out", "--out", str(tmp_path))
    assert code == 0
    data = json.loads(out)
    assert data["half"] == "held_out"
    assert (tmp_path / f"fp-held-out-k{data['k']}-unweighted.json").is_file()


def test_calibrate_measures_the_calibration_half_too(capsys, tmp_path):
    code, out = _run(capsys, "calibrate", "--half", "calibration", "--out", str(tmp_path))
    assert code == 0
    assert json.loads(out)["half"] == "calibration"


def test_ksweep_chooses_the_shipped_k(capsys, tmp_path):
    from mcpfanout.shingle import DEFAULT_K

    code, out = _run(capsys, "ksweep", "--out", str(tmp_path))
    assert code == 0
    assert json.loads(out)["choice"]["chosen_k"] == DEFAULT_K


def test_inventory_publishes_the_self_match_ceiling(capsys, tmp_path):
    code, out = _run(capsys, "inventory", "--out", str(tmp_path))
    assert code == 0
    data = json.loads(out)
    assert data["realistic_arguments"]["by_family"]
    assert "why_this_is_a_ceiling" in data


def test_rarity_exits_non_zero_because_the_weighting_did_not_help(capsys, tmp_path):
    """The exit code IS the result. A zero here would be the finding reversed."""
    code, out = _run(capsys, "rarity", "--out", str(tmp_path))
    assert code == 1
    assert json.loads(out)["verdict"] == "reverted"


# --- gate rule 7 ---------------------------------------------------------------------------------

def test_disclosure_check_is_clear_on_the_committed_example_run(capsys):
    code, out = _run(capsys, "disclosure-check", "--run", "example-concurrent")
    assert code == 0
    report = json.loads(out)
    assert report["verdict"] == "clear"
    assert report["servers_to_review"] == []
    assert "_redacted_run" in report, (
        "a redacted run's disclosure report must say that both sides of the comparison are "
        "relabelled, or it reads as a check against the committed declaration")


def test_disclosure_check_is_undeterminable_without_a_declaration(capsys, tmp_path):
    """Unevaluated is not the same as satisfied, and the exit code says so."""
    missing = tmp_path / "nothing.json"
    code, out = _run(capsys, "disclosure-check", "--run", "example-sequential",
                     "--declared", str(missing))
    assert code == 1
    assert json.loads(out)["verdict"] == "undeterminable"


# --- prep-context, the addon's input -------------------------------------------------------------

def test_prep_context_digests_the_bait_without_storing_it(capsys, tmp_path):
    out_path = tmp_path / "context.json"
    code, _ = _run(capsys, "prep-context", "--context-dir", "corpus/context",
                   "--out", str(out_path))
    assert code == 0
    text = out_path.read_text(encoding="utf-8")
    assert "CANARY_" not in text, "the digested context carries a plaintext canary"
    assert json.loads(text)


def test_the_parser_exposes_every_command_the_makefile_calls():
    """A Makefile target pointing at a subcommand that no longer exists fails at the worst time."""
    parser = cli.build_parser()
    actions = [a for a in parser._subparsers._group_actions if hasattr(a, "choices")]
    commands = set(actions[0].choices)
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    for command in sorted(commands):
        if command in ("run", "control-compare", "bench-verify", "prep-context", "prep-positive"):
            continue  # needs Docker, a control run, or a bench run
        assert command in makefile, f"the CLI has `{command}` and no make target reaches it"
