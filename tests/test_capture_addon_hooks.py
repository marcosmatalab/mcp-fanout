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
        (control / "active_calls.json").write_text(json.dumps(control_payload), encoding="utf-8")

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


def _active_call(args_digests=None):
    """One in-flight call, in the list shape the driver publishes.

    A list even with one entry: the count of in-flight calls is what separates a content match
    that discriminated from one that had nothing to discriminate against, so the addon has to
    read it rather than assume it.
    """
    return {"run_id": "t", "server_id": "fetch",
            "active_calls": [{"call_id": "fetch-c000", "traceparent": TRACEPARENT,
                              "args_present": True,
                              "args_digests": list(args_digests or [])}]}


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
    assert row["occurrence"] == "observed"
    assert row["active_calls_in_window"] == 1


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
        (f'{{"token": "{secret}"}}').encode()))

    rec = _recorder(tmp_path, _active_call(digests))
    rec.request(_FakeFlow(_FakeRequest(path=f"/v1/lookup?token={secret}", body=b"")))
    rec.done()
    row = json.loads((tmp_path / "flows.jsonl").read_text().splitlines()[0])
    assert row["causal"] is True, row
    assert row["causal_channel"] == "target"
    assert row["provenance"] == "arguments"
    # One call in flight, so the match discriminated nothing and the window count says so.
    assert row["active_calls_in_window"] == 1
    assert row["matching_calls_in_window"] == 1
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


# ---------------------------------------------------------------------------------------------
# The structural matcher, driven through the ADDON rather than through match.py.
#
# tests/test_structural_attribution.py tests the rules. These test that the addon actually
# publishes them into a Flow, which is a separate failure: `make selftest` serialises the new
# fields and never sets them, because its synthetic path does not run this hook. Without these,
# the claim that number 5 comes from persisted data rests on unit tests of a function the capture
# layer might not be calling.
# ---------------------------------------------------------------------------------------------

def _wave(*arg_dicts, salt=b"test-salt"):
    """Several in-flight calls with their token digests, as drive_wave publishes them."""
    from mcpfanout import structure as _S
    from mcpfanout.redact import Redactor
    r = Redactor(salt=salt)
    calls = []
    for i, args in enumerate(arg_dicts):
        calls.append({"call_id": f"fetch-c{i:03d}", "traceparent": TRACEPARENT,
                      "args_present": True, "args_digests": [],
                      "token_digests": sorted(
                          r.token_digest_set(_S.tokens_of_arguments(args)))})
    return {"run_id": "t", "server_id": "fetch", "active_calls": calls, "phase": "driving"}


RUNBOOK = {"url": "https://example.net/docs/deploy/runbook"}
ROLLBACK = {"url": "https://example.net/docs/deploy/rollback"}
DEEPER = {"url": "https://example.net/docs/deploy/runbook?section=rollback-steps"}
ROOT = {"url": "https://example.net/", "max_length": 2000}


def _row(tmp_path, payload, host, path):
    rec = _recorder(tmp_path, payload)
    rec.request(_FakeFlow(_FakeRequest(host=host, path=path)))
    rec.done()
    return [json.loads(l) for l in (tmp_path / "flows.jsonl").open()][-1]


def test_the_addon_attributes_a_flow_by_structural_containment(tmp_path):
    row = _row(tmp_path, _wave(RUNBOOK, ROLLBACK), "example.net", "/docs/deploy/rollback")
    assert row["structural_match"] is True
    assert row["structural_candidates"] == 1
    assert row["candidate_token_count"] == 4
    assert row["call_id"] == "fetch-c001", "attributed to the call that actually caused it"


def test_the_addon_refuses_a_flow_whose_only_candidate_does_not_discriminate(tmp_path):
    """The robots.txt case, end to end. The root call is contained and must not be credited."""
    row = _row(tmp_path, _wave(RUNBOOK, ROLLBACK, ROOT), "example.net", "/robots.txt")
    assert row["structural_contained"] == 1, "the root call is contained: its only token is host"
    assert row["structural_candidates"] == 0
    assert row["structural_match"] is False
    assert row["call_id"] is None, "never handed back to the call discrimination rejected"


def test_the_addon_records_the_subset_loss_rather_than_guessing(tmp_path):
    """Threat 18 through the capture layer: contained, not a candidate, and visible as both."""
    row = _row(tmp_path, _wave(RUNBOOK, DEEPER, ROOT), "example.net", "/docs/deploy/runbook")
    assert row["structural_contained"] == 2
    assert row["structural_candidates"] == 0
    assert row["non_discriminating_calls"] == 2
    assert row["call_id"] is None


def test_the_addon_flags_a_constant_client_path(tmp_path):
    """The content denominator has to be computable from the record, or it is not a denominator."""
    row = _row(tmp_path, _wave(RUNBOOK), "example.net", "/robots.txt")
    assert row["constant_client_path"] is True
    assert _row(tmp_path, _wave(RUNBOOK), "example.net",
                "/docs/deploy/runbook")["constant_client_path"] is False


def test_no_token_of_plaintext_reaches_the_flow_record(tmp_path):
    """Negative 2, checked where the bytes are actually written to disk."""
    row = _row(tmp_path, _wave(RUNBOOK, ROLLBACK), "example.net", "/docs/deploy/rollback")
    blob = json.dumps(row)
    for token in ("runbook", "rollback", "deploy", "docs"):
        assert token not in blob, f"{token!r} reached the persisted record"


def test_a_flow_carrying_nothing_of_ours_is_not_attributed(tmp_path):
    row = _row(tmp_path, _wave(RUNBOOK, ROLLBACK), "other.example.org", "/unrelated/path")
    assert row["structural_match"] is False and row["structural_contained"] == 0
    assert row["call_id"] is None
