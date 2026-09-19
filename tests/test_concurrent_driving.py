"""Concurrent waves: the capability CONTENT_UNIQUE needs to exist at all.

The driver could only hold one call in flight, so the strongest attribution grade was
unreachable and the project's thesis unmeasurable. These tests cover the two mechanics that had
to change: a client that keeps another request's response instead of discarding it, and a wave
that publishes its whole in-flight set before sending any of it.
"""

import json
import sys
from pathlib import Path

import pytest

from mcpfanout.driver import (CallSpec, StdioMCPClient, args_digests_for, drive_wave,
                              publish_active_calls)
from mcpfanout.redact import Redactor


def _mock_cmd() -> list[str]:
    return [sys.executable, str(Path(__file__).parent / "mock_server.py")]


def _active(control_dir: Path) -> dict:
    return json.loads((control_dir / "active_calls.json").read_text())


def test_responses_arriving_out_of_order_are_not_discarded():
    """Without a pending map, awaiting id 1 would throw away the answer to id 2 and hang.

    Sends three requests before reading anything, then collects them in REVERSE order, which is
    the case a single-request client cannot survive.
    """
    with StdioMCPClient(_mock_cmd()) as client:
        client.initialize()
        rids = [client.send_request("tools/call",
                                    {"name": "search", "arguments": {"q": str(i)}})
                for i in range(3)]
        for rid in reversed(rids):
            assert client.await_response(rid, method="tools/call")


def test_a_wave_publishes_its_whole_in_flight_set_before_sending(tmp_path):
    """The window count is what separates CONTENT_UNIQUE from CONTENT_MATCH_UNCONTESTED.

    If the set were published one call at a time, the addon would see a window of 1 for every
    flow and the strongest grade would stay unreachable even under real concurrency.
    """
    control = tmp_path / "control"
    r = Redactor(salt=b"t")
    specs = [CallSpec("search", {"q": f"fragment-number-{i}-padded-out"}) for i in range(5)]
    with StdioMCPClient(_mock_cmd()) as client:
        client.initialize()
        results = drive_wave(client, specs, run_id="t", server_id="bench",
                             redactor=r, control_dir=control)
    assert len(results) == 5 and all(x.ok for x in results), [x.error for x in results]
    assert [x.call_id for x in results] == [f"bench-c{i:03d}" for i in range(5)]
    # Every call in the wave got its own traceparent.
    assert len({x.traceparent for x in results}) == 5


def test_the_in_flight_set_is_cleared_after_the_wave(tmp_path):
    """Egress after a wave must be unattributed, not pinned to the wave that just finished.

    This is what makes the bench's "task still alive after the response" case meaningful: a time
    window cannot attribute what happens outside it, and the harness must not pretend otherwise.
    """
    control = tmp_path / "control"
    r = Redactor(salt=b"t")
    with StdioMCPClient(_mock_cmd()) as client:
        client.initialize()
        drive_wave(client, [CallSpec("search", {"q": "x"})], run_id="t", server_id="bench",
                   redactor=r, control_dir=control)
    assert _active(control)["active_calls"] == []


def test_publish_active_calls_is_the_single_writer_of_the_control_file(tmp_path):
    """Two writers with two notions of the payload is how the addon reads something nobody wrote.

    The phase is part of that payload and therefore part of the contract: an empty in-flight set has
    several meanings (the launcher is still downloading, the process is handshaking, a call just
    returned) and only one of them makes a flow impossible to attribute to a call. The addon cannot
    tell them apart from the list alone, so the driver states which it is.
    """
    control = tmp_path / "control"
    publish_active_calls(control, "run", "srv", [{"call_id": "c0", "traceparent": "tp",
                                                  "args_present": False, "args_digests": []}],
                         phase="driving")
    d = _active(control)
    assert d == {"run_id": "run", "server_id": "srv", "phase": "driving",
                 "active_calls": [{"call_id": "c0", "traceparent": "tp",
                                   "args_present": False, "args_digests": []}]}


def test_argument_digests_are_empty_for_an_argument_less_call():
    """An argument-less call has nothing that can travel, so it must contribute no digests.

    Otherwise it would compete for content matches it cannot possibly have produced.
    """
    r = Redactor(salt=b"t")
    assert args_digests_for(CallSpec("t", {}), r) == []
    assert args_digests_for(CallSpec("t", {"q": "a-long-enough-fragment-here"}), r)
