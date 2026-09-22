"""The two phase B passes: labelled, never merged, and reported under the condition that produced them.

Phase B is driven twice, sequentially and concurrently, and the two results are two experimental
conditions rather than two samples of one (docs/PROTOCOL.md, phase B). Everything here protects that
separation, because the way it fails is silent: one distribution over two conditions, with a label
naming one of them, is unreadable afterwards and looks fine.

What is covered:

- the ladder a server is driven at, which is capped by a declared claim about the server AND by the
  arithmetic of the corpus;
- the refusal to drive a second pass into a run that already holds one;
- the pass label reaching the aggregate, and the grade distribution being split by how many calls
  were actually in flight;
- number 5 saying which condition it is reporting, in both directions: a sequential run must say its
  grades are a restatement of the regime, a concurrent one must say there is no ground truth here.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from mcpfanout.aggregate import Run, number_5
from mcpfanout.record import (PASS_CONCURRENT, PASS_SEQUENTIAL, Flow, RunManifest, ToolCall,
                              write_jsonl, write_manifest)

REPO = Path(__file__).resolve().parent.parent


def _drive_all():
    """Load harness/drive_all.py by path: it is a script, not an installed module.

    Imported here rather than reimplemented because the ladder logic is a published claim (which N
    a server is driven at) and a second copy in the test would let the two drift.
    """
    spec = importlib.util.spec_from_file_location("drive_all_under_test",
                                                  REPO / "harness" / "drive_all.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flow(**kw) -> Flow:
    """A Flow with the fields these tests care about; the rest are neutral."""
    base = dict(run_id="r", server_id="s", call_id=None, ts=1.0, dest_host="api.example.org",
                dest_ip="203.0.113.1", scheme="https", method="POST", body_observed=True,
                our_traceparent_present=False, target_bytes=10, target_matched_bytes=0,
                body_bytes=100, body_matched_bytes=0, matched_refs=[], causal=False,
                causal_channel="none", node_category="remote_leaf", has_time_and_pid=True,
                occurrence="observed", provenance="none", active_calls_in_window=1,
                matching_calls_in_window=0)
    base.update(kw)
    return Flow(**base)


def _run(pass_name: str, flows: list[Flow], calls: list[ToolCall] | None = None) -> Run:
    manifest = RunManifest(run_id="r", created="1970-01-01T00:00:00Z", salt_fixed=True, k=16, w=8,
                           corpus_sha256="0" * 64, server_ids=["s"], pass_name=pass_name)
    return Run(manifest, calls or [], flows)


# --- The ladder.

@pytest.mark.parametrize("cap,corpus,expected", [
    (10, 10, [2, 5, 10]),
    (10, 6, [2, 5]),
    (5, 10, [2, 5]),
    (2, 4, [2]),
    (3, 3, [2]),
    (1, 10, []),      # a cap of one cannot hold a wave: no rung, and the caller reports it
    (10, 1, []),      # nor can a corpus of one
])
def test_the_ladder_respects_both_the_declared_cap_and_the_corpus(cap, corpus, expected):
    """A rung needs a server that can take N and a corpus that has N distinct calls.

    The corpus limit is not a technicality: padding a corpus to reach a rung would mean inventing
    arguments to fill a number, which is the opposite of the realism rule the concurrent corpus is
    written under (corpus/concurrent/README.md).
    """
    assert _drive_all().concurrency_levels(cap, corpus) == expected


def test_every_registry_server_reaches_at_least_the_first_rung():
    """A server that cannot be driven at N >= 2 would be in the concurrent run contributing nothing."""
    import yaml
    mod = _drive_all()
    registry = yaml.safe_load((REPO / "registry" / "servers.yaml").read_text())
    for server in registry["servers"]:
        corpus = json.loads((REPO / server["concurrent_corpus_ref"]).read_text())
        levels = mod.concurrency_levels(int(server["max_concurrency"]), len(corpus))
        assert levels, f"{server['id']}: no rung fits"
        assert levels[0] == 2, f"{server['id']}: {levels}"


def test_the_ladder_matches_the_bench_levels():
    """Same rungs as bench/waves.json, or the phase A comparison has nothing to stand on."""
    mod = _drive_all()
    waves = json.loads((REPO / "bench" / "waves.json").read_text())
    bench_levels = {n for cell in waves["discrimination_cells"] for n in cell["n"]}
    assert bench_levels <= set(mod.CONCURRENCY_LADDER), (
        f"the bench drove {sorted(bench_levels)} and the ladder is {mod.CONCURRENCY_LADDER}")


# --- The refusal to merge.

def test_a_second_pass_is_refused_into_a_run_that_already_holds_one(tmp_path, monkeypatch):
    """Merging two conditions into one distribution is the one error no footnote can undo."""
    run_dir = tmp_path / "20260919T000000Z-sequential"
    run_dir.mkdir()
    write_manifest(run_dir / "manifest.json",
                   RunManifest(run_id=run_dir.name, created="1970-01-01T00:00:00Z",
                               salt_fixed=True, k=16, w=8, corpus_sha256="0" * 64,
                               server_ids=["fetch"], pass_name=PASS_SEQUENTIAL))
    mod = _drive_all()
    monkeypatch.setattr(sys, "argv", [
        "drive_all.py", "--registry", str(REPO / "registry" / "servers.yaml"),
        "--run-dir", str(run_dir), "--mode", PASS_CONCURRENT, "--only", "fetch"])
    monkeypatch.chdir(REPO)
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert "already" in str(exc.value) and PASS_SEQUENTIAL in str(exc.value)


# --- The label, and what it changes in the report.

def test_the_pass_label_reaches_number_5():
    out = number_5(_run(PASS_CONCURRENT, [_flow(active_calls_in_window=5)]))
    assert out["pass"] == PASS_CONCURRENT


def test_an_unlabelled_run_is_reported_as_unlabelled_rather_than_guessed():
    """A run whose driving condition was not recorded must not have one inferred from its flows.

    "Driven sequentially on purpose" and "happened to contain no concurrency" are different claims,
    and only one of them licenses reading the grade distribution as a property of the servers.
    """
    out = number_5(_run("", [_flow()]))
    assert out["pass"] == "unlabelled"


def test_the_grades_are_split_by_how_many_calls_were_in_flight():
    """A pooled grade figure cannot show discrimination decaying as N grows, which is the result."""
    flows = [
        _flow(active_calls_in_window=2, matching_calls_in_window=1, causal=True),
        _flow(active_calls_in_window=5, matching_calls_in_window=3, causal=True),
        _flow(active_calls_in_window=5, matching_calls_in_window=1, causal=True),
        _flow(active_calls_in_window=10),
    ]
    out = number_5(_run(PASS_CONCURRENT, flows))
    by_n = out["grades_by_window_size"]
    assert by_n["2"] == {"CONTENT_UNIQUE": 1}
    assert by_n["5"] == {"CONTENT_AMBIGUOUS": 1, "CONTENT_UNIQUE": 1}
    assert set(by_n["10"]) == {"UNATTRIBUTED"}
    # The split must account for every flow, or it is a second, quieter figure.
    assert sum(sum(g.values()) for g in by_n.values()) == len(flows)


def test_the_split_and_the_pooled_grades_cannot_disagree():
    flows = [_flow(active_calls_in_window=n, matching_calls_in_window=1, causal=True)
             for n in (2, 2, 5, 10)]
    out = number_5(_run(PASS_CONCURRENT, flows))
    pooled = {g: c for g, c in out["attribution_grades"].items() if c}
    from collections import Counter
    split = Counter()
    for bucket in out["grades_by_window_size"].values():
        split.update(bucket)
    assert dict(split) == pooled


def test_a_sequential_run_says_its_grades_are_a_restatement_of_the_regime():
    out = number_5(_run(PASS_SEQUENTIAL, [_flow(causal=True, matching_calls_in_window=1)]))
    assert out["sequential_driving"] is True
    assert out["attribution_grades"]["CONTENT_MATCH_UNCONTESTED"] == 1
    note = out["sequential_driving_note"]
    assert "expected outcome of the sequential pass" in note
    assert "concurrent pass" in note
    assert "concurrent_driving_note" not in out


def test_a_concurrent_run_says_there_is_no_ground_truth_in_it():
    """The figure invites exactly one wrong reading: that a strong grade here was verified."""
    out = number_5(_run(PASS_CONCURRENT, [_flow(active_calls_in_window=5,
                                                matching_calls_in_window=1, causal=True)]))
    assert out["sequential_driving"] is False
    note = out["concurrent_driving_note"]
    assert "NO ground truth" in note
    assert "phase A" in note
    assert "sequential_driving_note" not in out


def test_a_run_with_no_flows_claims_neither_regime():
    """A server that egressed nothing cannot tell you how it was driven.

    Found on the first concurrent smoke run: driven at N = 10 against a local control that opened no
    connection, the figure reported `sequential_driving: true` because the maximum window over zero
    flows is zero. False would have asserted concurrency nobody saw and True asserted a regime the
    pass did not have, so the answer is neither.
    """
    out = number_5(_run(PASS_CONCURRENT, []))
    assert out["sequential_driving"] is None
    assert "no outbound connection was observed" in out["no_flows_note"]
    assert "sequential_driving_note" not in out and "concurrent_driving_note" not in out
    assert out["strong_attribution_fraction"] == 0.0


def test_the_driving_summary_reports_errors_by_wave_size(tmp_path):
    """A grade distribution at N=10 means nothing if the waves at N=10 errored out."""
    from mcpfanout.aggregate import driving_summary
    calls = [ToolCall("r", "s", "c0", "t", True, "tp", wave_size=2),
             ToolCall("r", "s", "c1", "t", True, "tp", wave_size=2, ok=False, error="boom"),
             ToolCall("r", "s", "c2", "t", False, "tp", wave_size=10, ok=False, error="boom")]
    out = driving_summary(_run(PASS_CONCURRENT, [], calls))
    assert out["calls_total"] == 3 and out["calls_errored"] == 2
    assert out["by_wave_size"]["2"] == {"calls": 2, "ok": 1, "errored": 1,
                                       "with_arguments": 2, "stdout_noise_lines": 0}
    assert out["by_wave_size"]["10"]["errored"] == 1


def test_a_run_directory_name_carries_its_pass():
    """So a listing of docs/figures/ distinguishes two incomparable artifacts without opening them."""
    run_sh = (REPO / "harness" / "run.sh").read_text()
    assert 'RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-${LABEL}"' in run_sh
