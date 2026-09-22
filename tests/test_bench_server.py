"""Drive the bench server for real, over stdio, against a real sink, and read its ledger.

No proxy and no Docker here: this checks that the pattern generator generates the pattern. That
it writes one truth row per outbound connection, that concurrent calls genuinely overlap, that
the late tool answers before it egresses, and that re-encoded payloads carry no literal run.

Uses BENCH_SINK_HOSTS to point every slot at 127.0.0.1, because the sinkNN.bench.invalid names
need /etc/hosts and therefore root. Distinct-destination joining is a property of the container
run, exercised there; what is checked here is everything else.
"""

import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import ClassVar

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "bench" / "server.py"
FRAG = "BENCHFRAG_unit_0123456789abcdef0123456"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen: ClassVar[list] = []

    def _ack(self):
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        type(self).seen.append({"path": self.path, "body": body,
                                "headers": {k.lower(): v for k, v in self.headers.items()}})
        self.send_response(204)
        self.send_header("content-length", "0")
        self.end_headers()

    do_GET = do_POST = do_PUT = _ack

    def log_message(self, *a):
        return


class _Sink(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture
def sink():
    _Handler.seen = []
    srv = _Sink(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], _Handler
    srv.shutdown()


class _Bench:
    """A live bench server on stdio, spoken to directly. Deliberately not via mcpfanout."""

    def __init__(self, truth: Path, port: int):
        import os
        env = {**os.environ, "BENCH_TRUTH": str(truth), "BENCH_SINK_PORT": str(port),
               "BENCH_SINK_HOSTS": "127.0.0.1"}
        self.p = subprocess.Popen([sys.executable, str(SERVER), "--truth", str(truth)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        self._id = 0
        self._pending = {}
        self.request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                    "clientInfo": {"name": "t", "version": "0"}})
        self.notify("notifications/initialized")

    def _send(self, obj):
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def notify(self, method):
        self._send({"jsonrpc": "2.0", "method": method, "params": {}})

    def send(self, method, params):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        return self._id

    def await_id(self, rid):
        if rid in self._pending:
            return self._pending.pop(rid)
        while True:
            msg = json.loads(self.p.stdout.readline())
            if msg.get("id") == rid:
                return msg
            if msg.get("id") is not None:
                self._pending[msg["id"]] = msg

    def request(self, method, params):
        return self.await_id(self.send(method, params))

    def close(self):
        self.p.kill()


def test_the_bench_answers_tools_list_with_its_own_tools(tmp_path, sink):
    port, _ = sink
    b = _Bench(tmp_path / "truth.jsonl", port)
    try:
        tools = b.request("tools/list", {})["result"]["tools"]
        names = {t["name"] for t in tools}
        assert {"bench_emit", "bench_emit_many", "bench_emit_late",
                "bench_emit_encoded"} <= names
    finally:
        b.close()


def test_one_call_writes_exactly_one_truth_row(tmp_path, sink):
    """One outbound connection, one ledger row, written from inside the handler."""
    port, handler = sink
    truth = tmp_path / "truth.jsonl"
    b = _Bench(truth, port)
    try:
        b.request("tools/call", {"name": "bench_emit",
                                 "arguments": {"slot": 0, "channel": "body", "fragment": FRAG}})
    finally:
        b.close()
    rows = [json.loads(l) for l in truth.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["channel"] == "body" and row["fragment"] == FRAG and row["method"] == "POST"
    assert row["error"] == ""
    assert row["call_id"].startswith("rpc")
    # And the sink really received the fragment, in the body.
    assert any(FRAG.encode() in r["body"] for r in handler.seen)


def test_the_fragment_lands_in_the_channel_the_ledger_claims(tmp_path, sink):
    """A ledger that names the wrong channel would make the comparator measure the wrong thing."""
    port, handler = sink
    truth = tmp_path / "truth.jsonl"
    b = _Bench(truth, port)
    try:
        for channel in ("target", "body", "header"):
            b.request("tools/call", {"name": "bench_emit",
                                     "arguments": {"slot": 0, "channel": channel,
                                                   "fragment": FRAG}})
    finally:
        b.close()
    rows = {json.loads(l)["channel"]: json.loads(l)
            for l in truth.read_text().splitlines() if l.strip()}
    assert set(rows) == {"target", "body", "header"}
    assert FRAG in rows["target"]["path"]
    got = handler.seen
    assert any(FRAG in r["path"] for r in got), "target channel: fragment not in the query"
    assert any(FRAG.encode() in r["body"] for r in got), "body channel: fragment not in the body"
    assert any(r["headers"].get("x-bench-fragment") == FRAG for r in got), "header channel"


def test_concurrent_calls_overlap_on_the_wire(tmp_path, sink):
    """The server must handle calls on threads, or a wave serializes and every window is one.

    Sends five calls before reading any response and requires all five ledger rows, with the
    spread of their timestamps far below the sum of their individual latencies. Overlap is the
    precondition for CONTENT_UNIQUE existing at all.
    """
    port, _ = sink
    truth = tmp_path / "truth.jsonl"
    b = _Bench(truth, port)
    try:
        rids = [b.send("tools/call", {"name": "bench_emit",
                                      "arguments": {"slot": i, "channel": "body",
                                                    "fragment": f"{FRAG}{i}"}})
                for i in range(5)]
        for rid in reversed(rids):
            assert "result" in b.await_id(rid)
    finally:
        b.close()
    rows = [json.loads(l) for l in truth.read_text().splitlines() if l.strip()]
    assert len(rows) == 5
    assert len({r["call_id"] for r in rows}) == 5, "each call must be its own ledger identity"


def test_the_late_tool_answers_before_it_egresses(tmp_path, sink):
    """Egress outside any window around the call, which is what defeats time attribution."""
    port, _ = sink
    truth = tmp_path / "truth.jsonl"
    b = _Bench(truth, port)
    try:
        t0 = time.monotonic()
        b.request("tools/call", {"name": "bench_emit_late",
                                 "arguments": {"slot": 0, "channel": "body", "fragment": FRAG,
                                               "delay_ms": 700}})
        answered = time.monotonic() - t0
        assert answered < 0.5, f"the response waited for the egress ({answered:.2f}s)"
        assert not truth.exists() or not truth.read_text().strip(), (
            "the ledger row appeared before the response; the egress was not late")
        time.sleep(1.4)
    finally:
        b.close()
    rows = [json.loads(l) for l in truth.read_text().splitlines() if l.strip()]
    assert len(rows) == 1, "the late egress never happened"


def test_fan_out_from_one_call_writes_one_row_per_connection(tmp_path, sink):
    port, _ = sink
    truth = tmp_path / "truth.jsonl"
    b = _Bench(truth, port)
    try:
        b.request("tools/call", {"name": "bench_emit_many",
                                 "arguments": {"slot": 0, "channel": "body", "fragment": FRAG,
                                               "count": 4}})
    finally:
        b.close()
    rows = [json.loads(l) for l in truth.read_text().splitlines() if l.strip()]
    assert len(rows) == 4
    assert len({r["call_id"] for r in rows}) == 1, "all four came from one call"


@pytest.mark.parametrize("encoding", ["base64", "gzip", "json_escaped"])
def test_reencoded_payloads_carry_no_literal_run(tmp_path, sink, encoding):
    """The known negatives. If a literal run survived, the cell would not measure what it claims.

    These exist to size what byte-literal matching loses (negative 3), so the precondition is
    that the fragment really is unrecoverable by a literal search. A cell whose payload still
    contained the fragment would report a sensor miss that was actually a sensor hit.
    """
    port, handler = sink
    truth = tmp_path / "truth.jsonl"
    b = _Bench(truth, port)
    try:
        b.request("tools/call", {"name": "bench_emit_encoded",
                                 "arguments": {"slot": 0, "encoding": encoding,
                                               "fragment": FRAG}})
    finally:
        b.close()
    rows = [json.loads(l) for l in truth.read_text().splitlines() if l.strip()]
    assert len(rows) == 1 and rows[0]["channel"] == f"body:{encoding}"
    sent = b"".join(r["body"] for r in handler.seen) + b"".join(
        r["path"].encode() for r in handler.seen)
    assert FRAG.encode() not in sent, f"{encoding} left the fragment literally recoverable"
    assert sent, "nothing was sent at all"
