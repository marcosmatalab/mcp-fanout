"""Drive the capture addon's hooks with fake flows, and require the result to serialise.

The capture layer shipped with a defect that made a run silently empty, and no test could have
caught it because nothing ever called request() or done(). The defect: a bool field was assigned
b"" through Python short-circuiting, so json.dumps raised inside done() and the buffered flows
for the whole run were lost. An empty flows.jsonl reads as "no server egressed anything", which
is the most expensive wrong answer this harness can give.

These tests use a hand-rolled stand-in for mitmproxy's flow object rather than mitmproxy itself,
because the capture extra is not installed for `make verify` (pyproject keeps the test path
dependency-light on purpose) and because the hook contract we depend on is small: request has
raw_content, headers, pretty_host, scheme and method, and the flow has server_conn.peername.
Trade-off: if mitmproxy changes that contract, these tests keep passing while the real capture
breaks. They are a guard on our logic, not on the integration, and the integration is covered by
actually running a capture.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parent.parent / "src" / "mcpfanout" / "capture_addon.py"
TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01"


class _FakeRequest:
    def __init__(self, body=b"", headers=None, host="api.example.net",
                 scheme="https", method="GET", path="/v1/ping"):
        self.raw_content = body
        self.headers = headers or {}
        self.pretty_host = host
        self.scheme = scheme
        self.method = method
        # mitmproxy's request.path is the request target: path plus query, not the absolute URL.
        # The addon must read this and not req.url, or the host ends up in the matched channel.
        self.path = path


class _FakeConn:
    def __init__(self, peername=("93.184.216.34", 443)):
        self.peername = peername


class _FakeFlow:
    def __init__(self, request, peername=("93.184.216.34", 443)):
        self.request = request
        self.server_conn = _FakeConn(peername)


def _recorder(tmp_path, control_payload=None):
    """Load the addon with its run dir redirected, optionally with an active call published."""
    control = tmp_path / "control"
    control.mkdir(parents=True, exist_ok=True)
    if control_payload is not None:
        (control / "current_call.json").write_text(json.dumps(control_payload), encoding="utf-8")

    fullname = "__mitmproxy_script__.capture_addon_hooks"
    saved_path, saved_env = list(sys.path), dict(os.environ)
    sys.path.insert(0, str(ADDON.parent))
    os.environ.update({"MCPFANOUT_RUNDIR": str(tmp_path),
                       "MCPFANOUT_CONTROL": str(control),
                       "MCPFANOUT_RUNID": "t",
                       "MCPFANOUT_SALT": "test-salt"})
    os.environ.pop("MCPFANOUT_CONTEXT", None)
    try:
        spec = importlib.util.spec_from_file_location(fullname, str(ADDON))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.addons[0]
    finally:
        sys.path[:] = saved_path
        os.environ.clear()
        os.environ.update(saved_env)
        sys.modules.pop(fullname, None)


def _active_call():
    return {"run_id": "t", "server_id": "fetch", "call_id": "fetch-c000",
            "traceparent": TRACEPARENT, "args_present": True, "args_digests": []}


def test_empty_body_with_an_active_call_still_serialises(tmp_path):
    """The exact shipped defect: active call, empty body, no traceparent header.

    `bool(tp) and (tp == header_tp or (body and tp.encode() in body))` returns b"" here, not
    False, and that bytes value made done() raise and drop the run's entire capture.
    """
    rec = _recorder(tmp_path, _active_call())
    rec.request(_FakeFlow(_FakeRequest(body=b"")))
    rec.done()

    lines = [l for l in (tmp_path / "flows.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 1, "the flow was dropped; done() could not serialise it"
    row = json.loads(lines[0])
    assert row["our_traceparent_present"] is False
    assert isinstance(row["our_traceparent_present"], bool)


def test_every_field_of_a_flow_is_json_native(tmp_path):
    """A non-JSON value anywhere in a Flow kills its line. Name the field, not just the failure."""
    from dataclasses import asdict
    rec = _recorder(tmp_path, _active_call())
    rec.request(_FakeFlow(_FakeRequest(body=b"")))
    allowed = (str, int, float, bool, type(None), list, dict)
    offenders = {k: type(v).__name__ for k, v in asdict(rec._buffer[0]).items()
                 if not isinstance(v, allowed)}
    assert not offenders, f"non-JSON field types in Flow: {offenders}"


def test_attribution_comes_from_the_active_call(tmp_path):
    """dest_host, server_id and call_id are the smoke test's minimum viable line."""
    rec = _recorder(tmp_path, _active_call())
    rec.request(_FakeFlow(_FakeRequest(host="example.net")))
    rec.done()
    row = json.loads((tmp_path / "flows.jsonl").read_text().splitlines()[0])
    assert row["dest_host"] == "example.net"
    assert row["server_id"] == "fetch"
    assert row["call_id"] == "fetch-c000"
    assert row["body_observed"] is True


def test_no_active_call_attributes_nothing_rather_than_guessing(tmp_path):
    """Egress with no call in flight is real data (a server phoning home), not an error.

    It must be recorded unattributed instead of being pinned on whichever call ran last.
    """
    rec = _recorder(tmp_path, control_payload=None)
    rec.request(_FakeFlow(_FakeRequest(host="telemetry.example.net")))
    rec.done()
    row = json.loads((tmp_path / "flows.jsonl").read_text().splitlines()[0])
    assert row["server_id"] == "" and row["call_id"] is None


def test_traceparent_in_the_header_is_detected(tmp_path):
    """Number 3 depends on this: did the server forward our trace context downstream?"""
    rec = _recorder(tmp_path, _active_call())
    rec.request(_FakeFlow(_FakeRequest(headers={"traceparent": TRACEPARENT})))
    rec.done()
    row = json.loads((tmp_path / "flows.jsonl").read_text().splitlines()[0])
    assert row["our_traceparent_present"] is True


def test_traceparent_in_the_body_is_detected(tmp_path):
    rec = _recorder(tmp_path, _active_call())
    rec.request(_FakeFlow(_FakeRequest(body=b'{"trace":"' + TRACEPARENT.encode() + b'"}',
                                       method="POST")))
    rec.done()
    row = json.loads((tmp_path / "flows.jsonl").read_text().splitlines()[0])
    assert row["our_traceparent_present"] is True


def test_one_unserialisable_flow_does_not_destroy_the_others(tmp_path):
    """The failure mode that made this whole layer produce an empty file."""
    rec = _recorder(tmp_path, _active_call())
    rec.request(_FakeFlow(_FakeRequest(host="good-one.example.net")))
    rec.request(_FakeFlow(_FakeRequest(host="good-two.example.net")))
    rec._buffer[0].dest_ip = b"\x00not-json"  # force the shape of the original defect
    rec.done()
    lines = [l for l in (tmp_path / "flows.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 1, "a single bad record must cost one record, not the run"
    assert json.loads(lines[0])["dest_host"] == "good-two.example.net"


def test_done_appends_across_calls(tmp_path):
    """mitmdump can restart inside a run; a second flush must not truncate the first."""
    rec = _recorder(tmp_path, _active_call())
    rec.request(_FakeFlow(_FakeRequest(host="first.example.net")))
    rec.done()
    rec.request(_FakeFlow(_FakeRequest(host="second.example.net")))
    rec.done()
    hosts = [json.loads(l)["dest_host"]
             for l in (tmp_path / "flows.jsonl").read_text().splitlines() if l.strip()]
    assert hosts == ["first.example.net", "second.example.net"]


def test_the_request_target_is_matched_not_only_the_body(tmp_path):
    """A GET carrying the canary in its query string must come out EFECTIVO, via the target.

    This is the whole reason the matcher was changed: with body-only matching this flow scored
    DECLARADO, and number 5 was structurally zero for every GET-based server.
    """
    secret = "AKIA_EXAMPLE_SECRET_TOKEN_0123456789"
    from mcpfanout.redact import Redactor
    digests = sorted(Redactor(salt=b"test-salt").kgram_digest_set(
        ('{"token": "%s"}' % secret).encode()))
    call = dict(_active_call(), args_digests=digests)

    rec = _recorder(tmp_path, call)
    rec.request(_FakeFlow(_FakeRequest(path=f"/v1/lookup?token={secret}", body=b"")))
    rec.done()
    row = json.loads((tmp_path / "flows.jsonl").read_text().splitlines()[0])
    assert row["state"] == "EFECTIVO", row
    assert row["causal_channel"] == "target"
    assert row["target_matched_bytes"] == 0, "no context index here, so only the causal key hit"
    assert row["body_bytes"] == 0


def test_the_addon_reads_the_target_not_the_absolute_url(tmp_path):
    """Including scheme and host would manufacture self-matches and measure nothing real."""
    rec = _recorder(tmp_path, _active_call())
    req = _FakeRequest(host="api.example.net", path="/v1/ping")
    req.url = "https://api.example.net/v1/ping"  # present, and must be ignored
    rec.request(_FakeFlow(req))
    rec.done()
    row = json.loads((tmp_path / "flows.jsonl").read_text().splitlines()[0])
    assert row["target_bytes"] == len("/v1/ping"), (
        "target_bytes covers more than path+query; the absolute URL leaked in")
