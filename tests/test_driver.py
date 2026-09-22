"""Test the MCP stdio driver against the mock server."""

import sys
import time
from pathlib import Path

import pytest

from mcpfanout.driver import (
    PROTOCOL_VERSION,
    CallSpec,
    DriveResult,
    ServerTimeout,
    StdioMCPClient,
    drive,
    new_traceparent,
)

# harness/ is a directory of scripts, not a package, so it is not on the path by install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
from probe import CANDIDATE_PROTOCOLS, probe

# Revisions that removed the initialize handshake, so neither driver.initialize() nor a
# handshake probe can speak them. Listed explicitly rather than "anything after 2025-11-25":
# a date comparison would silently start failing on a future revision that reinstates a
# handshake, and would pass a revision that removes something else we do depend on.
POST_HANDSHAKE_EXCLUDED = {"2026-07-28"}


def _mock_cmd() -> list[str]:
    return [sys.executable, str(Path(__file__).parent / "mock_server.py")]


def test_traceparent_shape():
    tp = new_traceparent()
    parts = tp.split("-")
    assert parts[0] == "00" and len(parts[1]) == 32 and len(parts[2]) == 16 and parts[3] == "01"


def test_drive_mock_server():
    corpus = [
        CallSpec("search", {"query": "hello"}),
        CallSpec("search", {}),  # argument-less call: args_present must be False
    ]
    results = drive(_mock_cmd(), corpus, run_id="t", server_id="mock")
    assert len(results) == 2
    assert all(r.ok for r in results), [r.error for r in results]
    assert results[0].args_present is True
    assert results[1].args_present is False
    # Each call carries a distinct traceparent (the attribution key).
    assert results[0].traceparent != results[1].traceparent


# --- Protocol negotiation. These have teeth only because mock_server.py rejects what it does
# --- not support; against the old mirroring mock every assertion below passed vacuously.

def test_protocol_version_is_a_handshake_revision():
    """The constant must name a revision that actually has an initialize method.

    Anchors the fix for the shipped defect: PROTOCOL_VERSION said "2026-07-28", which removed
    the initialize handshake (SEP-2575), so the driver announced a protocol it does not speak.
    If someone later bumps the constant to a post-handshake revision, the driver has to be
    rewritten to server/discover in the same change, and this test is where they find out.
    """
    assert PROTOCOL_VERSION not in POST_HANDSHAKE_EXCLUDED, (
        f"{PROTOCOL_VERSION} has no initialize method; driver.initialize() cannot speak it"
    )
    assert PROTOCOL_VERSION == "2025-11-25"


def test_driver_handshake_accepted_by_a_server_that_only_supports_our_revision():
    """The constant is not just well-formed, it is the one a 2025-11-25 server accepts."""
    results = drive(_mock_cmd(), [CallSpec("search", {"q": "x"})], run_id="t", server_id="mock",
                    env={"MOCK_SUPPORTED_PROTOCOLS": "2025-11-25"})
    assert results[0].ok, results[0].error


def test_driver_handshake_rejected_when_server_speaks_only_another_revision():
    """A mismatch must surface, per call and with the reason, and must not end the run.

    This assertion changed deliberately, and the reason is a measurement lost to it. It used to
    require ``drive`` to RAISE on a handshake rejection, on the principle that a mismatch must not
    be papered over. The principle is right; raising was the wrong mechanism for it. A startup
    failure is a property of ONE server, and on the first ten-server capture one server that could
    not start (mcp-server-git, no git binary in the image) raised out of drive, through drive_all,
    and ended the whole run after two servers. Nine working servers were lost to one broken one.

    So the failure is now recorded rather than thrown: every call of that server's corpus comes
    back ok=False carrying the error text, which is what "surfaces" has to mean for a harness whose
    output is a record. Nothing is papered over, because the reason is in the record and drive_all
    prints it; what changed is that the finding no longer takes the other nine servers with it.
    """
    results = drive(_mock_cmd(), [CallSpec("search", {}), CallSpec("search", {"q": "x"})],
                    run_id="t", server_id="mock",
                    env={"MOCK_SUPPORTED_PROTOCOLS": "2024-11-05"})
    assert len(results) == 2, "every call of the corpus is accounted for, driven or not"
    assert not any(r.ok for r in results)
    for r in results:
        assert "unsupported protocolVersion" in r.error
    # No traceparent was ever sent, so the record must not imply one was.
    assert all(r.traceparent == "" for r in results)


def test_probe_negotiates_down_to_what_the_server_supports():
    """The probe's fallback ladder has to actually walk. Needs a rejecting mock to mean anything."""
    out = probe(_mock_cmd(), {"MOCK_SUPPORTED_PROTOCOLS": "2024-11-05"})
    assert out["ok"], out
    assert out["protocol_version_used"] == "2024-11-05"
    assert out["server_protocol_version"] == "2024-11-05"
    # The rejections on the way down are kept as data, not discarded.
    assert [a["protocol_version_tried"] for a in out["attempts"]] == ["2025-11-25", "2025-06-18",
                                                                     "2025-03-26"]


def test_probe_candidate_list_excludes_post_handshake_revisions():
    """A handshake probe cannot legitimately negotiate a revision that deleted initialize."""
    assert CANDIDATE_PROTOCOLS[0] == PROTOCOL_VERSION
    assert not POST_HANDSHAKE_EXCLUDED & set(CANDIDATE_PROTOCOLS)


# --- Bounded reads. A server that starts and says nothing used to hang the harness forever.

def test_hung_server_times_out_and_is_recorded_as_a_failed_call():
    """The timeout must produce data, not a crash: a hung server is a finding about that server."""
    started = time.monotonic()
    with (StdioMCPClient(_mock_cmd(), {"MOCK_HANG": "1"}, read_timeout=2.0) as client,
          pytest.raises(ServerTimeout)):
        client.initialize()
    elapsed = time.monotonic() - started
    assert elapsed < 30, f"read was not bounded: waited {elapsed:.1f}s"


def test_probe_of_a_hung_server_reports_not_ok_instead_of_hanging():
    out = probe(_mock_cmd(), {"MOCK_HANG": "1"}, startup_timeout=1.0, list_timeout=1.0)
    assert out["ok"] is False
    assert out["tools"] == [] and out["attempts"]


# --- Servers that corrupt their own stdout. MCP stdio reserves stdout for JSON-RPC and sends
# --- logging to stderr; mcp-server-fetch 2026.8.18 lets npm write to stdout during a tools/call.

def test_non_json_stdout_is_skipped_and_counted_not_fatal():
    """Reproduces the real failure: npm output on the JSON-RPC channel.

    Before this, _read() called json.loads on every line, so one npm progress line made every
    call to that server fail with "Expecting value: line 2 column 1" -- a server we can observe
    egressing became a server we could not measure at all.
    """
    results = drive(_mock_cmd(), [CallSpec("search", {"q": "x"})], run_id="t", server_id="mock",
                    env={"MOCK_STDOUT_NOISE": "1"})
    assert results[0].ok, results[0].error
    assert results[0].stdout_noise_lines > 0, "noise was absorbed silently instead of counted"


def test_stdout_noise_reaches_the_persisted_record(tmp_path):
    """Counting it in memory is no use if the run does not carry it out to the reader."""
    from mcpfanout.record import ToolCall, read_jsonl
    calls = tmp_path / "calls.jsonl"
    drive(_mock_cmd(), [CallSpec("search", {})], run_id="t", server_id="mock",
          env={"MOCK_STDOUT_NOISE": "1"}, calls_path=calls)
    rows = list(read_jsonl(calls, ToolCall))
    assert rows[0].stdout_noise_lines > 0
    assert rows[0].ok is True


def test_a_failed_call_persists_its_reason(tmp_path):
    """A call that errored after egressing and one that never reached the network are opposite
    findings, and only the error text tells them apart."""
    from mcpfanout.record import ToolCall, read_jsonl
    calls = tmp_path / "calls.jsonl"
    drive(_mock_cmd(), [CallSpec("no_such_tool", {})], run_id="t", server_id="mock",
          calls_path=calls)
    rows = list(read_jsonl(calls, ToolCall))
    assert rows[0].ok is False
    assert "method not found" in rows[0].error or "error" in rows[0].error.lower()


def test_drive_result_and_toolcall_do_not_drift():
    """Two code paths build a ToolCall from a DriveResult: driver.drive and drive_all.main.

    When only one of them learned about ok/error/stdout_noise_lines, the persisted run claimed
    every call succeeded with zero noise while the driver was reporting seven noise lines. A
    field that exists on both records has to be carried by both paths, so this test names the
    overlap instead of trusting two call sites to stay in step.
    """
    from dataclasses import fields

    from mcpfanout.record import ToolCall
    shared = {f.name for f in fields(DriveResult)} & {f.name for f in fields(ToolCall)}
    assert {"ok", "error", "stdout_noise_lines"} <= shared
    src = (Path(__file__).resolve().parent.parent / "harness" / "drive_all.py").read_text()
    call = src.split("all_calls.append(ToolCall(")[1].split("))")[0]
    for name in sorted(shared - {"run_id", "server_id"}):
        assert name in call, f"drive_all drops ToolCall.{name} and it silently defaults"
