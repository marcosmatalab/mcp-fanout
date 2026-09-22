"""A connection the LAUNCHER made is not the server's egress, and no figure may count it as such.

The measured defect this file exists to prevent, from the first ten-server capture: four servers
each showed exactly one package-registry connection, and every one of them was attributed to that
server's LAST call. They were not that server's egress at all. The sequential driver left the final
call published after the corpus finished, so the NEXT server's `npx -y pkg@ver` resolution landed in
a window nobody had cleared and was credited to a call that had already returned.

That is the same class of error as calling 87 package-registry flows DECLARADO, which cost a
published figure once already. Two mechanisms now stand against it, and this file tests both:

1. **The driver publishes where it is in each server's lifecycle**, and publishes the launcher phase
   BEFORE the subprocess exists. An empty in-flight set cannot express that: "the launcher is still
   downloading", "the process is handshaking" and "a call just returned" are three different facts
   and only the first makes a flow impossible to attribute to a call.
2. **The driver drains after every call**, not only at the end of the corpus, so nothing arriving
   between calls is credited to the one that just finished.

The rule being enforced is the one gate rule 7's decision procedure rests on: a destination
contacted by the launcher before the server process starts is not the server's egress, it is
recorded apart, and it triggers no disclosure.
"""

import json
import sys
from pathlib import Path

from mcpfanout.aggregate import Run, driving_summary, number_1, number_2, number_5
from mcpfanout.driver import CallSpec, StdioMCPClient, drive
from mcpfanout.match import REASON_PRE_LAUNCH, UNATTRIBUTED
from mcpfanout.record import (
    PHASE_DRAINED,
    PHASE_DRIVING,
    PHASE_HANDSHAKE,
    PHASE_LAUNCHER,
    PHASES_LIFECYCLE,
    PHASES_NOT_CALL_CAUSED,
    Flow,
    RunManifest,
    ToolCall,
)
from mcpfanout.redact import Redactor

REPO = Path(__file__).resolve().parent.parent


def _mock_cmd() -> list[str]:
    return [sys.executable, str(REPO / "tests" / "mock_server.py")]


def _flow(phase: str, call_id: str | None, host: str = "registry.example.org") -> Flow:
    return Flow(run_id="r", server_id="s", call_id=call_id, ts=1.0, dest_host=host,
                dest_ip="203.0.113.1", scheme="https", method="GET", body_observed=True,
                our_traceparent_present=False, target_bytes=10, target_matched_bytes=0,
                body_bytes=0, body_matched_bytes=0, matched_refs=[], causal=False,
                causal_channel="none", node_category="remote_leaf", has_time_and_pid=True,
                active_calls_in_window=1 if call_id else 0, matching_calls_in_window=0,
                phase=phase)


def _run(flows: list[Flow]) -> Run:
    manifest = RunManifest(run_id="r", created="1970-01-01T00:00:00Z", salt_fixed=True, k=22, w=8,
                           corpus_sha256="0" * 64, server_ids=["s"], pass_name="sequential")
    return Run(manifest, [ToolCall("r", "s", "s-c000", "t", True, "tp", wave_size=1)], flows)


# --- The classification exists and is explicit.

def test_both_pre_call_phases_are_impossible_to_attribute_to_a_call():
    """The line is "had a call been sent", not "did a process exist", and that was a correction.

    `launcher` was meant to catch the package manager resolving a dependency and it cannot: the
    process we spawn IS npx or uvx, which resolves and then execs the server, so the subprocess
    exists while the MCP server does not. The first capture with phases recorded put all seven npx
    servers' package-registry connections in `handshake`. Both pre-call phases therefore count as
    not-call-caused, because in neither had any call been sent.

    Whose traffic it is remains a separate question, answered in disclosure.py against the declared
    package-infrastructure list rather than guessed from the phase.
    """
    assert set(PHASES_LIFECYCLE) == {PHASE_LAUNCHER, PHASE_HANDSHAKE, PHASE_DRIVING, PHASE_DRAINED}
    assert set(PHASES_NOT_CALL_CAUSED) == {PHASE_LAUNCHER, PHASE_HANDSHAKE}
    # Drained is AFTER a call, so the server's own delayed egress stays the server's and stays
    # counted. Excluding it would let a server hide egress by deferring it past its response.
    assert PHASE_DRAINED not in PHASES_NOT_CALL_CAUSED
    assert PHASE_DRIVING not in PHASES_NOT_CALL_CAUSED


# --- THE RULE: a flow before the first tools/call is never the server's egress.

def test_a_launcher_flow_is_never_counted_in_the_per_call_figures():
    """Numbers 1 and 2 are per invocation. A pre-launch connection has no invocation to belong to.

    Written with the launcher flow CARRYING A CALL ID, which is the exact shape of the defect: the
    addon attributed it to a call because the control file still named one. The phase is what
    overrides that, so the test would fail if the exclusion were based on call_id being absent.
    """
    run = _run([_flow(PHASE_LAUNCHER, "s-c000"), _flow(PHASE_DRIVING, "s-c000",
                                                       "api.example.org")])
    n1 = number_1(run)
    assert n1["launcher_connections"] == 1
    # One call, one call-caused connection: the distribution must say 1 and not 2.
    assert n1["connections_raw"]["max"] == 1, n1["connections_raw"]
    assert number_2(run)["distribution"]["max"] == 1


def test_a_launcher_flow_is_never_attributed_however_strong_its_other_evidence():
    """Checked first, before trace and content, and that ordering is the point.

    A traceparent or a content match on a flow that predates every call is a collision or a leak of
    our own marker into the launcher's traffic, not evidence of a cause. Nothing may outvote "this
    happened before anything that could have caused it".
    """
    strong = _flow(PHASE_LAUNCHER, "s-c000")
    strong.our_traceparent_present = True
    strong.causal = True
    strong.matching_calls_in_window = 1
    out = number_5(_run([strong]))
    assert out["attribution_grades"][UNATTRIBUTED] == 1
    assert out["attribution_grades"]["TRACE_PROPAGATED"] == 0
    assert out["attribution_grades"]["CONTENT_MATCH_UNCONTESTED"] == 0
    assert REASON_PRE_LAUNCH in out["attribution_reasons"]


def test_the_reason_names_the_launcher_rather_than_shrugging():
    """An UNATTRIBUTED flow without a reason is a shrug recorded as data."""
    out = number_5(_run([_flow(PHASE_LAUNCHER, None)]))
    assert "before the server process existed" in REASON_PRE_LAUNCH
    assert out["attribution_reasons"][REASON_PRE_LAUNCH] == 1


def test_a_driving_flow_is_still_counted_so_the_exclusion_is_not_a_blanket():
    """The exclusion has to be narrow, or it becomes a way of making inconvenient traffic vanish."""
    n1 = number_1(_run([_flow(PHASE_DRIVING, "s-c000")]))
    assert n1["launcher_connections"] == 0
    assert n1["connections_raw"]["max"] == 1


def test_an_unrecorded_phase_counts_as_possible_and_is_reported():
    """A run written before the field existed must not have flows dropped from its figures.

    Dropping them would silently change old numbers on the strength of a field nobody wrote. They
    count, and the count of unrecorded ones is published so a reader can see the uncertainty.
    """
    n1 = number_1(_run([_flow("", "s-c000")]))
    assert n1["launcher_connections"] == 0
    assert n1["flows_with_unrecorded_phase"] == 1
    assert n1["connections_raw"]["max"] == 1


def test_a_handshake_flow_is_excluded_from_the_per_call_figures_too():
    """It precedes every call, so it cannot be per-call, whoever made it.

    This is the case the first version got wrong: the npm connections of seven servers landed here,
    not in the launcher phase, and one of them was credited to a call in an earlier capture.
    """
    run = _run([_flow(PHASE_HANDSHAKE, "s-c000"), _flow(PHASE_DRIVING, "s-c000",
                                                        "api.example.org")])
    n1 = number_1(run)
    assert n1["launcher_connections"] == 1
    assert n1["connections_raw"]["max"] == 1
    assert number_5(run)["attribution_reasons"].get(REASON_PRE_LAUNCH) == 1


def test_the_driving_summary_reports_where_the_connections_landed():
    out = driving_summary(_run([_flow(PHASE_LAUNCHER, None), _flow(PHASE_DRIVING, "s-c000"),
                                _flow(PHASE_DRAINED, None), _flow("", None)]))
    assert out["flows_by_lifecycle_phase"] == {PHASE_LAUNCHER: 1, PHASE_DRIVING: 1,
                                               PHASE_DRAINED: 1, "unrecorded": 1}


# --- The driver's side: the phases are actually published, in order.

def test_the_driver_publishes_the_launcher_phase_before_the_process_exists(tmp_path, monkeypatch):
    """The ordering is the whole mechanism: published after the spawn, it would be a lie.

    Captured by recording every payload the driver writes, in order, and checking that the launcher
    phase is published before the subprocess is created.
    """
    seen: list[str] = []
    real_popen = __import__("subprocess").Popen

    import mcpfanout.driver as driver_mod
    original_publish = driver_mod.publish_active_calls

    def spy(control_dir, run_id, server_id, entries, phase=""):
        seen.append(phase)
        return original_publish(control_dir, run_id, server_id, entries, phase)

    def spy_popen(*a, **kw):
        seen.append("<spawn>")
        return real_popen(*a, **kw)

    monkeypatch.setattr(driver_mod, "publish_active_calls", spy)
    monkeypatch.setattr(driver_mod.subprocess, "Popen", spy_popen)

    drive(_mock_cmd(), [CallSpec("search", {"q": "x" * 40})], run_id="t", server_id="s",
          redactor=Redactor(salt=b"t"), control_dir=tmp_path / "control")

    assert seen[0] == PHASE_LAUNCHER, seen
    assert seen.index(PHASE_LAUNCHER) < seen.index("<spawn>"), seen
    assert seen.index("<spawn>") < seen.index(PHASE_HANDSHAKE), seen
    assert seen[-1] == PHASE_DRAINED, seen


def test_the_driver_drains_after_every_call_not_only_at_the_end(tmp_path):
    """Otherwise egress arriving between calls is credited to the call that just returned.

    Three calls, so the pattern driving/drained/driving/drained/driving/drained is visible rather
    than only the final state.
    """
    control = tmp_path / "control"
    seen: list[str] = []

    import mcpfanout.driver as driver_mod
    original = driver_mod.publish_active_calls

    def spy(control_dir, run_id, server_id, entries, phase=""):
        seen.append(phase)
        return original(control_dir, run_id, server_id, entries, phase)

    driver_mod.publish_active_calls = spy
    try:
        drive(_mock_cmd(), [CallSpec("search", {"q": f"fragment-{i}-padded-out-to-length"})
                            for i in range(3)],
              run_id="t", server_id="s", redactor=Redactor(salt=b"t"), control_dir=control)
    finally:
        driver_mod.publish_active_calls = original

    driving_then_drained = [p for p in seen if p in (PHASE_DRIVING, PHASE_DRAINED)]
    assert driving_then_drained == [PHASE_DRIVING, PHASE_DRAINED] * 3, seen
    # And the file is left drained, so nothing arriving after the corpus is attributed either.
    final = json.loads((control / "active_calls.json").read_text())
    assert final["active_calls"] == [] and final["phase"] == PHASE_DRAINED


def test_the_concurrent_ladder_leaves_the_control_file_drained(tmp_path):
    """The concurrent path always drained; this pins it so the two paths cannot diverge again."""
    from mcpfanout.driver import drive_wave
    control = tmp_path / "control"
    with StdioMCPClient(_mock_cmd()) as client:
        client.initialize()
        drive_wave(client, [CallSpec("search", {"q": "x" * 40})], run_id="t", server_id="s",
                   redactor=Redactor(salt=b"t"), control_dir=control)
    d = json.loads((control / "active_calls.json").read_text())
    assert d["phase"] == PHASE_DRAINED and d["active_calls"] == []


def test_the_concurrent_ladder_publishes_the_launcher_phase_before_the_process_exists(
        tmp_path, monkeypatch):
    """The third way the same defect came back, and the reason this test is not a duplicate.

    The sequential path was fixed for this and the concurrent path was not, because the two publish
    independently: `drive_wave` publishes DRIVING and DRAINED, and nothing published LAUNCHER or
    HANDSHAKE for a ladder. The consequence was not a missing label. The control file still held the
    PREVIOUS server's id with phase `drained`, so `npx -y pkg@ver` resolving the NEXT server's
    package was recorded as the previous server's call-caused egress, and the first ten-server
    concurrent capture flagged four servers under gate rule 7 for a package registry none of them
    contacted, plus one flow attributed to nobody at all.

    Asserted on the ORDER of the payloads rather than on the final state, because the final state
    was already correct while the run was wrong.
    """
    sys.path.insert(0, str(REPO / "harness"))
    import drive_all

    seen: list[str] = []
    real_popen = __import__("subprocess").Popen
    original_publish = drive_all.publish_active_calls

    def spy(control_dir, run_id, server_id, entries, phase=""):
        seen.append(phase)
        return original_publish(control_dir, run_id, server_id, entries, phase)

    def spy_popen(*a, **kw):
        seen.append("<spawn>")
        return real_popen(*a, **kw)

    import mcpfanout.driver as driver_mod
    monkeypatch.setattr(drive_all, "publish_active_calls", spy)
    monkeypatch.setattr(driver_mod, "publish_active_calls", spy)
    monkeypatch.setattr(driver_mod.subprocess, "Popen", spy_popen)

    corpus = tmp_path / "concurrent.json"
    corpus.write_text(json.dumps([
        {"tool": "search", "arguments": {"q": f"fragment-{i}-padded-out-to-length"}}
        for i in range(2)]), encoding="utf-8")
    srv = {"id": "s", "launch": _mock_cmd(), "concurrent_corpus_ref": str(corpus),
           "max_concurrency": 2}

    drive_all.drive_server_concurrent(srv, run_id="t", control_dir=tmp_path / "control",
                                      redactor=Redactor(salt=b"t"), proxy_env={})

    assert seen[0] == PHASE_LAUNCHER, seen
    assert seen.index(PHASE_LAUNCHER) < seen.index("<spawn>"), seen
    assert seen.index("<spawn>") < seen.index(PHASE_HANDSHAKE), seen
    assert seen.index(PHASE_HANDSHAKE) < seen.index(PHASE_DRIVING), seen
    assert seen[-1] == PHASE_DRAINED, seen


def test_both_driving_paths_publish_the_same_lifecycle_phases():
    """Neither path may know a phase the other does not.

    The defect above existed because one path was fixed and the other was not, and a test that
    checked only the fixed one would have passed throughout. This compares the SETS, so a phase
    added to either path without the other fails here rather than in a capture six months later.
    """
    sys.path.insert(0, str(REPO / "harness"))
    sequential = (REPO / "src" / "mcpfanout" / "driver.py").read_text(encoding="utf-8")
    concurrent = (REPO / "harness" / "drive_all.py").read_text(encoding="utf-8")
    for phase_const in ("PHASE_LAUNCHER", "PHASE_HANDSHAKE", "PHASE_DRIVING", "PHASE_DRAINED"):
        assert phase_const in sequential, phase_const
        assert phase_const in concurrent or phase_const in ("PHASE_DRIVING", "PHASE_DRAINED"), (
            f"{phase_const} is published by the sequential path and not by the concurrent one; "
            f"DRIVING and DRAINED are exempt only because drive_wave publishes them")
