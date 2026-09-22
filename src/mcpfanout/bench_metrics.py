"""The instrument block: capture recall, attribution precision, false provenance matches.

These three exist ONLY for the phase A bench and cannot be computed anywhere else. Recall needs a
denominator of transfers we caused on purpose; precision needs a known cause to check a claim
against. A third-party server supplies neither, so a recall figure quoted from a phase B run
would be a number with no denominator (docs/PROTOCOL.md, gate rule 8).

THREE FILES, THREE AUTHORS, and that is what makes the comparison mean anything:

  bench_truth.jsonl  written by bench/server.py from inside its own handler. What the bench
                     actually sent, per outbound connection. The capture addon never reads it.
  bench_plan.jsonl   written by bench/drive_bench.py. What the harness intended to drive: which
                     call used which destination slot, in which cell. Intent, not observation.
  flows.jsonl        written by the capture addon. What the sensor saw and how it graded it.

The join is on DESTINATION HOST. Each bench call egresses to its own host, the plan says which
call owns which host, and the ledger says what actually went there. The sensor reads the host off
the wire independently and attributes by trace, content and window, never by hostname, so
comparing its answer to the ledger's is a genuine test rather than a restatement. That
independence is asserted in tests/test_bench_metrics.py, because it is the assumption the whole
figure rests on.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from . import match as _match

# Channels the sensor is built to read. A fragment carried anywhere else is a KNOWN NEGATIVE, so
# it is excluded from the denominator of the attribution figures and counted separately: charging
# the sensor for a channel it does not claim to read would understate precision while telling
# nobody anything. Recall is unaffected, because the connection still happened and still had to
# be seen.
MATCHED_CHANNELS = ("target", "body")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _frac(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def compute(run_dir: str | Path, truth_path: str | Path | None = None) -> dict:
    """Compare the bench's ledger against the sensor's flows. Returns the instrument block."""
    run_dir = Path(run_dir)
    truth = _read_jsonl(Path(truth_path) if truth_path else run_dir / "bench_truth.jsonl")
    plan = _read_jsonl(run_dir / "bench_plan.jsonl")
    flows = _read_jsonl(run_dir / "flows.jsonl")

    if not truth or not plan:
        return {"name": "instrument_block", "ok": False,
                "reason": "no bench truth ledger or no bench plan in this run; these metrics "
                          "are computable only for a phase A bench run",
                "command": "make bench"}

    slot_of_call = {r["call_id"]: r["slot"] for r in plan}
    plan_of_host: dict[str, dict] = {}
    for row in plan:
        plan_of_host[_host_for_slot(row["slot"])] = row

    # Ledger rows that never left (the bench recorded its own failure) are not the sensor's fault
    # and must not enter recall's denominator.
    sent = [r for r in truth if not r.get("error")]
    failed_to_send = len(truth) - len(sent)

    truth_by_host: dict[str, list[dict]] = defaultdict(list)
    for row in sent:
        truth_by_host[row["dest_host"]].append(row)

    bench_hosts = set(truth_by_host)
    bench_flows = [f for f in flows if f.get("dest_host") in bench_hosts]
    flows_by_host: dict[str, list[dict]] = defaultdict(list)
    for f in bench_flows:
        flows_by_host[f["dest_host"]].append(f)

    # --- Capture recall. Did the sensor see what we know we sent.
    observed = sum(min(len(flows_by_host.get(h, [])), len(rows))
                   for h, rows in truth_by_host.items())
    recall = {
        "connections_sent": len(sent),
        "connections_observed": observed,
        "capture_recall": _frac(observed, len(sent)),
        "connections_the_bench_failed_to_send": failed_to_send,
        "flows_to_bench_hosts": len(bench_flows),
        "hosts_sent_to_but_never_observed": sorted(h for h in truth_by_host
                                                   if h not in flows_by_host),
    }

    # --- Attribution. Per flow, what the sensor claimed against what the ledger says.
    graded: list[dict] = []
    for host, fl in flows_by_host.items():
        expected_call = plan_of_host.get(host, {}).get("call_id")
        cell = plan_of_host.get(host, {}).get("cell", "unknown")
        channel = plan_of_host.get(host, {}).get("channel", "")
        for f in fl:
            grade, _ = _grade_of(f)
            graded.append({"cell": cell, "channel": channel, "host": host,
                           "grade": grade, "claimed_call": f.get("call_id"),
                           "expected_call": expected_call,
                           "in_matched_channel": channel in MATCHED_CHANNELS,
                           "provenance": f.get("provenance"),
                           "fragment_present": plan_of_host.get(host, {})
                           .get("fragment_present", False)})

    strong = [g for g in graded if g["grade"] in _match.STRONG_ATTRIBUTION]
    strong_claimed = [g for g in strong if g["claimed_call"]]
    strong_correct = [g for g in strong_claimed if g["claimed_call"] == g["expected_call"]]
    false_strong = [g for g in strong_claimed if g["claimed_call"] != g["expected_call"]]

    attribution = {
        "flows_graded": len(graded),
        "strong_attributions": len(strong),
        "strong_attributions_with_a_named_call": len(strong_claimed),
        "strong_attributions_correct": len(strong_correct),
        "false_strong_attributions": len(false_strong),
        # The sensor-gate criterion with tolerance zero. Reported as a count, never as a rate:
        # a rate invites "only 2%", and one false strong attribution destroys the evidentiary
        # claim the product rests on.
        "attribution_precision": _frac(len(strong_correct), len(strong_claimed)),
    }

    # --- Per cell, expected against observed. The mixture cell is why this is per flow.
    cells: dict[str, dict] = {}
    for g in graded:
        c = cells.setdefault(g["cell"], {"flows": 0, "grades": {}, "correct_call": 0,
                                         "wrong_call": 0, "no_call": 0})
        c["flows"] += 1
        c["grades"][g["grade"]] = c["grades"].get(g["grade"], 0) + 1
        if not g["claimed_call"]:
            c["no_call"] += 1
        elif g["claimed_call"] == g["expected_call"]:
            c["correct_call"] += 1
        else:
            c["wrong_call"] += 1
    for row in plan:
        cells.setdefault(row["cell"], {"flows": 0, "grades": {}, "correct_call": 0,
                                       "wrong_call": 0, "no_call": 0})["expect"] = \
            row.get("expect", "")

    # --- False provenance. The sensor claiming material of ours where the ledger says none went.
    no_material = [g for g in graded if not g["fragment_present"]]
    false_prov = [g for g in no_material
                  if g["provenance"] in (_match.PROVENANCE_ARGUMENTS, _match.PROVENANCE_CONTEXT,
                                         _match.PROVENANCE_BOTH)]
    provenance = {
        "flows_with_no_material_sent": len(no_material),
        "false_provenance_matches": len(false_prov),
        "false_provenance_rate": _frac(len(false_prov), len(no_material)),
    }

    # --- Known negatives: what byte-literal matching loses, as a figure rather than a caveat.
    unmatched_channel = [g for g in graded if not g["in_matched_channel"] and g["fragment_present"]]
    known_negatives = {
        "flows_carrying_material_in_an_unread_channel": len(unmatched_channel),
        "of_which_the_sensor_attributed_strongly": len(
            [g for g in unmatched_channel if g["grade"] in _match.STRONG_ATTRIBUTION]),
        "note": "headers and re-encoded payloads are channels byte-literal matching cannot see "
                "(negative 3). Measured to size the loss, documented as a permanent known "
                "negative, never as debt",
    }

    return {"name": "instrument_block", "ok": True,
            "capture": recall, "attribution": attribution, "provenance": provenance,
            "known_negatives": known_negatives, "per_cell": cells,
            "calls_planned": len(slot_of_call),
            "command": "make bench"}


def _host_for_slot(slot: int) -> str:
    """Must match bench/server.py's mapping. Duplicated on purpose: see the note below.

    The bench cannot import this module and this module cannot import the bench, because that
    shared import would be the circularity the isolation exists to prevent. So the mapping is
    written twice and tests/test_bench_metrics.py asserts the two agree by reading the bench's
    source. Two copies with a test arbitrating beats one copy that breaks the isolation.
    """
    return f"sink{slot % 128:03d}.bench.invalid"


def _grade_of(flow: dict) -> tuple[str, str]:
    """Re-derive the attribution grade from a flow record, as the aggregate does."""
    return _match.grade_attribution(
        traceparent_present=bool(flow.get("our_traceparent_present")),
        argument_match=bool(flow.get("causal")),
        active_calls_in_window=int(flow.get("active_calls_in_window") or 0),
        matching_calls_in_window=int(flow.get("matching_calls_in_window") or 0),
        # A bench sink is never package infrastructure, so eligibility cannot mask a result here.
        eligible=True,
        has_time_and_pid=bool(flow.get("has_time_and_pid")),
    )
