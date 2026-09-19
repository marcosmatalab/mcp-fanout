"""The comparator: recall, precision, false provenance, computed over synthetic inputs.

Synthetic here is the right call and not a shortcut. A real bench run is Docker plus network and
cannot run in `make verify`, and what needs pinning is the ARITHMETIC and the JOIN, not the
capture. So these tests hand-build the three files, with the answers known by construction, and
require the comparator to reach them. The real run exercises the capture; this exercises the
comparison.

The most important test in this file is the last one: that the sensor's attribution does not use
the destination host, which is the comparator's join key. If it did, the precision figure would
be the sensor agreeing with the key it was handed, and it would look like a pass.
"""

import ast
import json
from pathlib import Path

import pytest

from mcpfanout import match as m
from mcpfanout.bench_metrics import MATCHED_CHANNELS, _host_for_slot, compute

REPO = Path(__file__).resolve().parent.parent


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _flow(host: str, *, call_id=None, causal=False, active=1, matching=0, tp=False,
          provenance="none") -> dict:
    return {"dest_host": host, "call_id": call_id, "causal": causal,
            "active_calls_in_window": active, "matching_calls_in_window": matching,
            "our_traceparent_present": tp, "has_time_and_pid": True,
            "provenance": provenance, "body_observed": True}


def _bench_run(tmp_path, *, truth, plan, flows) -> Path:
    _write(tmp_path / "bench_truth.jsonl", truth)
    _write(tmp_path / "bench_plan.jsonl", plan)
    _write(tmp_path / "flows.jsonl", flows)
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _plan_row(slot, call_id, cell, channel="body", expect="", fragment=True, n=2) -> dict:
    return {"slot": slot, "call_id": call_id, "cell": cell, "group": "discrimination_cells",
            "n": n, "tool": "bench_emit", "channel": channel, "expect": expect,
            "fragment_present": fragment}


def _truth_row(slot, call_id, channel="body", fragment="F" * 40, error="") -> dict:
    return {"call_id": call_id, "dest_host": _host_for_slot(slot), "path": "/bench/ingest",
            "method": "POST", "channel": channel, "fragment": fragment, "ts": 1.0,
            "error": error}


def test_a_run_without_a_bench_ledger_refuses_rather_than_reporting_zero(tmp_path):
    """These metrics have no denominator outside the bench, so absent inputs must not read as 0.0.

    A recall of 0.0 and "there was nothing to measure" are opposite findings, and a comparator
    that returned the first for the second would put an unfalsifiable figure in front of gate
    rule 8.
    """
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    out = compute(tmp_path)
    assert out["ok"] is False
    assert "phase A" in out["reason"]
    assert "capture" not in out


def test_capture_recall_counts_what_the_bench_knows_it_sent(tmp_path):
    run = _bench_run(
        tmp_path,
        truth=[_truth_row(0, "rpc1"), _truth_row(1, "rpc2"), _truth_row(2, "rpc3")],
        plan=[_plan_row(0, "bench-c000", "all_distinct"),
              _plan_row(1, "bench-c001", "all_distinct"),
              _plan_row(2, "bench-c002", "all_distinct")],
        # The sensor missed the third connection entirely.
        flows=[_flow(_host_for_slot(0)), _flow(_host_for_slot(1))],
    )
    out = compute(run)
    assert out["capture"]["connections_sent"] == 3
    assert out["capture"]["connections_observed"] == 2
    assert out["capture"]["capture_recall"] == 0.6667
    assert out["capture"]["hosts_sent_to_but_never_observed"] == [_host_for_slot(2)]


def test_a_connection_the_bench_failed_to_send_is_not_charged_to_the_sensor(tmp_path):
    """The bench recording its own failure is not a capture miss, and must leave the denominator."""
    run = _bench_run(
        tmp_path,
        truth=[_truth_row(0, "rpc1"), _truth_row(1, "rpc2", error="URLError: refused")],
        plan=[_plan_row(0, "bench-c000", "all_distinct"),
              _plan_row(1, "bench-c001", "all_distinct")],
        flows=[_flow(_host_for_slot(0))],
    )
    out = compute(run)
    assert out["capture"]["connections_sent"] == 1
    assert out["capture"]["capture_recall"] == 1.0
    assert out["capture"]["connections_the_bench_failed_to_send"] == 1


def test_a_correct_strong_attribution_counts_as_precision(tmp_path):
    """Concurrent window, fragment in one call: CONTENT_UNIQUE, and the named call is right."""
    run = _bench_run(
        tmp_path,
        truth=[_truth_row(0, "rpc1"), _truth_row(1, "rpc2")],
        plan=[_plan_row(0, "bench-c000", "all_distinct", expect="CONTENT_UNIQUE"),
              _plan_row(1, "bench-c001", "all_distinct", expect="CONTENT_UNIQUE")],
        flows=[_flow(_host_for_slot(0), call_id="bench-c000", causal=True, active=2, matching=1),
               _flow(_host_for_slot(1), call_id="bench-c001", causal=True, active=2, matching=1)],
    )
    out = compute(run)
    a = out["attribution"]
    assert a["strong_attributions"] == 2
    assert a["strong_attributions_correct"] == 2
    assert a["false_strong_attributions"] == 0
    assert a["attribution_precision"] == 1.0
    assert out["per_cell"]["all_distinct"]["grades"][m.CONTENT_UNIQUE] == 2


def test_a_strong_attribution_naming_the_wrong_call_is_a_false_strong(tmp_path):
    """The figure the sensor gate gives tolerance zero. It has to be countable, so it is counted.

    Reported as a count and not only as a rate: a rate invites "only 2%", and one false strong
    attribution destroys the evidentiary claim the whole product rests on.
    """
    run = _bench_run(
        tmp_path,
        truth=[_truth_row(0, "rpc1"), _truth_row(1, "rpc2")],
        plan=[_plan_row(0, "bench-c000", "all_distinct"),
              _plan_row(1, "bench-c001", "all_distinct")],
        flows=[_flow(_host_for_slot(0), call_id="bench-c001", causal=True, active=2, matching=1),
               _flow(_host_for_slot(1), call_id="bench-c001", causal=True, active=2, matching=1)],
    )
    out = compute(run)
    assert out["attribution"]["false_strong_attributions"] == 1
    assert out["attribution"]["attribution_precision"] == 0.5
    assert out["per_cell"]["all_distinct"]["wrong_call"] == 1


def test_the_ambiguous_cell_makes_no_strong_claim(tmp_path):
    """All N share the fragment, so content did not discriminate and nothing strong may be said."""
    run = _bench_run(
        tmp_path,
        truth=[_truth_row(0, "rpc1"), _truth_row(1, "rpc2")],
        plan=[_plan_row(0, "bench-c000", "all_shared", expect="CONTENT_AMBIGUOUS"),
              _plan_row(1, "bench-c001", "all_shared", expect="CONTENT_AMBIGUOUS")],
        flows=[_flow(_host_for_slot(0), causal=True, active=2, matching=2),
               _flow(_host_for_slot(1), causal=True, active=2, matching=2)],
    )
    out = compute(run)
    assert out["attribution"]["strong_attributions"] == 0
    assert out["per_cell"]["all_shared"]["grades"][m.CONTENT_AMBIGUOUS] == 2
    assert out["per_cell"]["all_shared"]["no_call"] == 2


def test_the_mixture_cell_is_judged_per_flow_not_in_aggregate(tmp_path):
    """The cell that cannot be passed by accident.

    Two calls share a fragment and two do not. Right counts with the wrong pairing must fail, so
    the comparator records the claimed call per flow rather than only tallying grades.
    """
    plan = [_plan_row(i, f"bench-c{i:03d}", "two_shared_rest_distinct", expect="mixture", n=4)
            for i in range(4)]
    truth = [_truth_row(i, f"rpc{i}") for i in range(4)]
    flows = [
        # Slots 0 and 1 shared the fragment: ambiguous, no call named.
        _flow(_host_for_slot(0), causal=True, active=4, matching=2),
        _flow(_host_for_slot(1), causal=True, active=4, matching=2),
        # Slot 2 unique and correctly named.
        _flow(_host_for_slot(2), call_id="bench-c002", causal=True, active=4, matching=1),
        # Slot 3 unique but named as slot 2's call: a false strong, and the aggregate tally of
        # grades alone would not see it.
        _flow(_host_for_slot(3), call_id="bench-c002", causal=True, active=4, matching=1),
    ]
    out = compute(_bench_run(tmp_path, truth=truth, plan=plan, flows=flows))
    cell = out["per_cell"]["two_shared_rest_distinct"]
    assert cell["grades"] == {m.CONTENT_AMBIGUOUS: 2, m.CONTENT_UNIQUE: 2}
    assert cell["correct_call"] == 1 and cell["wrong_call"] == 1 and cell["no_call"] == 2
    assert out["attribution"]["false_strong_attributions"] == 1


def test_a_provenance_claim_where_nothing_was_sent_is_a_false_match(tmp_path):
    """The sensor saying material of ours was present when the ledger says none went."""
    run = _bench_run(
        tmp_path,
        truth=[_truth_row(0, "rpc1", channel="none", fragment=""),
               _truth_row(1, "rpc2", channel="none", fragment="")],
        plan=[_plan_row(0, "bench-c000", "no_arguments", channel="none", fragment=False),
              _plan_row(1, "bench-c001", "no_arguments", channel="none", fragment=False)],
        flows=[_flow(_host_for_slot(0), provenance="arguments", active=2),
               _flow(_host_for_slot(1), provenance="none", active=2)],
    )
    out = compute(run)
    assert out["provenance"]["flows_with_no_material_sent"] == 2
    assert out["provenance"]["false_provenance_matches"] == 1
    assert out["provenance"]["false_provenance_rate"] == 0.5


def test_the_no_argument_cell_lands_unattributed_not_temporal(tmp_path):
    """The fourth discrimination cell, end to end through the comparator."""
    plan = [_plan_row(i, f"bench-c{i:03d}", "no_arguments", channel="none", fragment=False, n=5)
            for i in range(5)]
    truth = [_truth_row(i, f"rpc{i}", channel="none", fragment="") for i in range(5)]
    flows = [_flow(_host_for_slot(i), active=5) for i in range(5)]
    out = compute(_bench_run(tmp_path, truth=truth, plan=plan, flows=flows))
    cell = out["per_cell"]["no_arguments"]
    assert cell["grades"] == {m.UNATTRIBUTED: 5}
    assert m.TEMPORAL_ONLY not in cell["grades"]


def test_an_unread_channel_is_reported_as_a_known_negative_not_as_a_failure(tmp_path):
    """Charging the sensor for a channel it does not claim to read would understate precision."""
    run = _bench_run(
        tmp_path,
        truth=[_truth_row(0, "rpc1", channel="header")],
        plan=[_plan_row(0, "bench-c000", "header_channel", channel="header",
                        expect="UNATTRIBUTED")],
        flows=[_flow(_host_for_slot(0), active=5)],
    )
    out = compute(run)
    kn = out["known_negatives"]
    assert kn["flows_carrying_material_in_an_unread_channel"] == 1
    assert kn["of_which_the_sensor_attributed_strongly"] == 0
    assert "header" not in MATCHED_CHANNELS


def test_the_two_slot_to_host_mappings_agree():
    """The comparator and the bench each own a copy, because sharing one would break isolation.

    bench/server.py cannot import the harness and the harness cannot import the bench, so the
    mapping is written twice on purpose. This test is the arbiter: two copies with a test between
    them beats one copy that defeats the isolation the precision figure depends on.
    """
    src = (REPO / "bench" / "server.py").read_text()
    tree = ast.parse(src)
    template = next(n.value.value for n in ast.walk(tree)
                    if isinstance(n, ast.Assign)
                    and any(getattr(t, "id", "") == "SINK_HOST_TEMPLATE" for t in n.targets))
    max_slots = next(n.value.value for n in ast.walk(tree)
                     if isinstance(n, ast.Assign)
                     and any(getattr(t, "id", "") == "MAX_SLOTS" for t in n.targets))
    for slot in (0, 1, 7, 81, 127, 128, 200):
        assert _host_for_slot(slot) == template.format(slot=slot % max_slots), slot


def test_the_sensor_never_attributes_using_the_destination_host():
    """THE assumption the precision figure rests on, asserted against the source.

    The comparator joins a ledger row to a flow by destination host. If the sensor also used the
    host to decide which call caused a flow, precision would measure the sensor agreeing with the
    key it was handed, and it would read as a pass. So: grade_attribution takes no host argument,
    and the addon's choice of call_id is made from the in-flight set and the content match only.
    """
    import inspect
    sig = inspect.signature(m.grade_attribution)
    assert not any("host" in p or "dest" in p for p in sig.parameters), sig

    addon = ast.parse((REPO / "src" / "mcpfanout" / "capture_addon.py").read_text())
    picker = next(n for n in ast.walk(addon)
                  if isinstance(n, ast.Assign)
                  and any(getattr(t, "id", "") == "attributed" for t in n.targets))
    # The expression that picks the attributed call must not mention the host in any form.
    chosen = ast.dump(picker)
    for forbidden in ("pretty_host", "dest_host", "dest_ip"):
        assert forbidden not in chosen, f"the addon picks a call using {forbidden}"


# --- The bench's own precondition: fragments that cannot collide.

def test_no_two_fragments_in_a_discriminating_wave_share_a_kgram():
    """The precondition for the discrimination cells to measure anything at all.

    The first bench run reported CONTENT_AMBIGUOUS for every all_distinct flow, and the sensor
    was right every time: the fragments were "BENCHFRAG_<tag>_0123456789abcdef0123456", sharing a
    10-byte prefix and a 24-byte constant tail, both over k = 16. K-grams from the tail were in
    every call's argument digests, so every flow matched every call. A bench whose fragments
    collide does not measure discrimination, it measures its own collisions.
    """
    import sys
    sys.path.insert(0, str(REPO / "bench"))
    from drive_bench import _plan, _wave_specs  # noqa: E402

    from mcpfanout.shingle import DEFAULT_K, rolling_hashes

    index = 0
    checked = 0
    for cell, n, wave_id in _plan(REPO / "bench" / "waves.json"):
        specs = _wave_specs(cell, n, wave_id, first_slot=index)
        index += n
        frags = sorted({s.arguments["fragment"] for s in specs if s.arguments.get("fragment")})
        if cell["template"]["fragment_mode"] != "distinct" or len(frags) < 2:
            continue
        grams = {f: set(rolling_hashes(f.encode(), DEFAULT_K)) for f in frags}
        for i, a in enumerate(frags):
            for b in frags[i + 1:]:
                shared = grams[a] & grams[b]
                assert not shared, (
                    f"{cell['cell']}: fragments share {len(shared)} k-gram(s); the cell cannot "
                    f"distinguish one call from another")
                checked += 1
    assert checked, "no distinct-fragment wave was checked; the guard is not running"


def test_fragments_are_long_enough_to_be_detectable():
    """Shorter than k and a match is undetectable; barely over and it is luck."""
    import sys
    sys.path.insert(0, str(REPO / "bench"))
    from drive_bench import _fragment  # noqa: E402

    from mcpfanout.calibrate import K_MAX
    from mcpfanout.shingle import DEFAULT_K
    frag = _fragment("anything")

    # TWO bounds, and the pair is the requirement. Below: at least k + 8 bytes, so the fragment
    # carries at least nine k-grams and detection never hinges on one of them surviving. Above: not
    # longer than the top of the sweep range, because the k sweep has to be ABLE to observe bench
    # recall collapsing (docs/CALIBRATION.md, F1.2); a fragment longer than every k in the range
    # would make recall 1.0 everywhere and the curve could no longer show that it can fall at all.
    #
    # This replaced "at least 2 * k", which was a margin with no argument behind it and which
    # started failing the moment k was chosen by measurement: 40 bytes is 1.8 k at k = 22, and the
    # test called that "too short to match reliably" while the fragment in fact yields nineteen
    # k-grams. A heuristic that fails on a correct change is a heuristic, not an invariant.
    assert len(frag) >= DEFAULT_K + 8, f"{len(frag)} bytes leaves too few k-grams at k={DEFAULT_K}"
    assert len(frag) <= K_MAX, (
        f"{len(frag)} bytes exceeds the top of the sweep range ({K_MAX}), so the k sweep could no "
        f"longer observe bench recall falling anywhere in it")
