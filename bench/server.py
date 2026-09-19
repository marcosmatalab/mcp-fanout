"""The phase A bench MCP server: known egress to a destination we own, and its own truth ledger.

THE ISOLATION PROPERTY, which is the reason this file is written from scratch instead of reusing
the harness. This server imports NOTHING from mcpfanout and never reads the harness control
directory. It learns which tool call it is serving the only legitimate way: the call arrived on
its own stdin, over MCP stdio, addressed to it. If it instead discovered that by reading
active_calls.json, then measuring "did the sensor attribute correctly?" against "what does the
bench say?" would be comparing the sensor to a copy of itself, and any precision figure published
from it would be worth nothing. tests/test_bench_isolation.py fails if that ever changes.

So this file speaks enough JSON-RPC itself: initialize, notifications/initialized, tools/list,
tools/call. Duplicating a hundred lines of protocol is the price of a non-circular measurement,
and it is cheap at the price.

THE TRUTH LEDGER. From inside the handler, for every outbound connection it makes, this server
appends one line to BENCH_TRUTH: which call_id caused it, where it went, which fragment it
carried and in which channel, AND the exact bytes it sent (request target and body) together with
the arguments the call arrived with. That file is written only here, read only by the comparator
(mcpfanout.bench_metrics) and by the k sweep (mcpfanout.calibrate), and never read by the capture
addon.

Why the ledger holds payload bytes when the rest of the harness stores only digests. Negative 2
(docs/DOCTRINE.md) constrains what the OBSERVER stores about traffic it did not create. This file
is the opposite: it is the sender's own account of material the sender generated, all of it
synthetic and keyed from a published constant, in a run directory that is never committed. It has
always carried the fragment verbatim for exactly that reason. The bytes are needed because a
content-match recall curve over k cannot be recomputed from digests taken at one k, and the
alternative, re-running the bench once per value of k, would take an hour to answer a question the
sender already knows the answer to.

Threaded on purpose. Concurrency is not one bench case among eleven, it is the whole question:
CONTENT_UNIQUE cannot exist unless several calls are genuinely in flight at once. Each tools/call
is handled on its own thread so the outbound connections actually overlap; stdout is serialized by
a lock, because two threads writing JSON-RPC lines into one pipe would corrupt the channel exactly
the way mcp-server-fetch corrupts its own with npm output.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-11-25"

# Each concurrent slot gets its own destination hostname. That is what lets the comparator join a
# ledger row to an observed flow WITHOUT any shared mechanism: the sensor reads the host off the
# wire by itself and attributes by trace, content and window, never by hostname. The slot arrives
# as an INTEGER argument, never as a hostname, so the destination name cannot leak into the
# matchable argument material and manufacture a content match out of the destination itself.
SINK_HOST_TEMPLATE = "sink{slot:03d}.bench.invalid"
# One destination per CALL in the whole run, not per position within a wave. Sixteen slots reused
# across waves would make sink03 the destination of many calls, and the comparator's join would
# be ambiguous exactly where concurrency makes it interesting. The harness assigns a global slot
# index; the image maps this many names to loopback.
MAX_SLOTS = 128


def _sink_host(slot: int) -> str:
    """The destination for one slot.

    BENCH_SINK_HOSTS (comma separated) overrides the template. It exists so the bench can be
    unit tested without editing /etc/hosts, which needs root: a test passes 127.0.0.1 and
    exercises the protocol, the threading and the ledger. In the container the sinkNN names are
    mapped to loopback in the image and each slot therefore gets a DISTINCT destination, which
    is the join key the comparator needs. Distinctness is a property of the real run, not of the
    unit test, and the comparator says so when it cannot join.
    """
    override = os.environ.get("BENCH_SINK_HOSTS", "").strip()
    if override:
        hosts = [h.strip() for h in override.split(",") if h.strip()]
        return hosts[slot % len(hosts)]
    return SINK_HOST_TEMPLATE.format(slot=slot % MAX_SLOTS)

_stdout_lock = threading.Lock()
_truth_lock = threading.Lock()
_truth_path = ""


def _truth(row: dict) -> None:
    """Append one ledger row. The bench's own account of what it did, from inside the handler."""
    if not _truth_path:
        return
    line = json.dumps(row, sort_keys=True) + "\n"
    with _truth_lock:
        with open(_truth_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()


def _send(obj: dict) -> None:
    line = json.dumps(obj) + "\n"
    with _stdout_lock:
        sys.stdout.write(line)
        sys.stdout.flush()


def _sink_url(slot: int, path: str) -> str:
    port = os.environ.get("BENCH_SINK_PORT", "8099")
    return f"http://{_sink_host(slot)}:{port}{path}"


def _egress(call_id: str, slot: int, fragment: str, channel: str,
            arguments: dict | None = None) -> dict:
    """Make ONE outbound request carrying ``fragment`` in ``channel``, and record the truth.

    Channels are the three a real server can leak through, and the sensor currently reads two of
    them. The header case is included precisely because it is a known blind spot: measuring it
    sizes the gap instead of leaving it unstated.
    """
    host = _sink_host(slot)
    method, body, headers, path = "GET", None, {}, "/bench"

    if channel == "target":
        path = f"/bench/q?frag={fragment}"
    elif channel == "body":
        method, path = "POST", "/bench/ingest"
        body = json.dumps({"frag": fragment}).encode()
        headers["content-type"] = "application/json"
    elif channel == "header":
        headers["x-bench-fragment"] = fragment
        path = "/bench/hdr"
    elif channel == "none":
        path = "/bench/plain"
        fragment = ""
    else:
        raise ValueError(f"unknown channel {channel!r}")

    url = _sink_url(slot, path)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    error = ""
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except (urllib.error.URLError, OSError, socket.timeout) as exc:
        error = f"{type(exc).__name__}: {exc}"

    row = {"call_id": call_id, "dest_host": host, "path": path, "method": method,
           "channel": channel, "fragment": fragment, "ts": time.time(), "error": error,
           # The exact bytes on the wire, so a matcher question can be re-asked at any k without
           # re-running the bench. base64 because one cell sends gzip, and a ledger line has to
           # stay one line of valid JSON whatever the payload is.
           "request_target": path,
           "request_body_b64": base64.b64encode(body or b"").decode(),
           # What the call arrived with. The server's OWN knowledge (it came in on stdin), not
           # anything read from the harness, so the isolation property is untouched.
           "call_arguments": arguments or {}}
    _truth(row)
    return row


TOOLS = [
    {
        "name": "bench_emit",
        "description": "Make one outbound request to our own sink, carrying a fragment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer", "description": "which sink host to use"},
                "fragment": {"type": "string", "description": "the material to carry"},
                "channel": {"type": "string", "enum": ["target", "body", "header", "none"]},
            },
            "required": ["slot", "channel"],
        },
    },
    {
        "name": "bench_emit_many",
        "description": "Make several outbound requests for one call: fan-out from one call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer"},
                "fragment": {"type": "string"},
                "channel": {"type": "string", "enum": ["target", "body", "header", "none"]},
                "count": {"type": "integer", "description": "how many connections to open"},
            },
            "required": ["slot", "channel", "count"],
        },
    },
    {
        "name": "bench_emit_late",
        "description": "Answer first, then egress after a delay: egress outside any time window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer"},
                "fragment": {"type": "string"},
                "channel": {"type": "string", "enum": ["target", "body", "header", "none"]},
                "delay_ms": {"type": "integer"},
            },
            "required": ["slot", "channel"],
        },
    },
    {
        "name": "bench_emit_encoded",
        "description": "Carry the fragment re-encoded, which literal matching cannot see.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slot": {"type": "integer"},
                "fragment": {"type": "string"},
                "encoding": {"type": "string", "enum": ["base64", "gzip", "json_escaped"]},
            },
            "required": ["slot", "encoding"],
        },
    },
]
TOOL_NAMES = {t["name"] for t in TOOLS}


def _encode(fragment: str, encoding: str) -> bytes:
    import base64
    import gzip
    if encoding == "base64":
        return base64.b64encode(fragment.encode())
    if encoding == "gzip":
        return gzip.compress(fragment.encode())
    if encoding == "json_escaped":
        # Every character escaped as \uXXXX: valid JSON, same value, no literal run survives.
        return ("".join(f"\\u{ord(c):04x}" for c in fragment)).encode()
    raise ValueError(encoding)


def _handle_call(mid, params: dict) -> None:
    name = params.get("name")
    args = params.get("arguments") or {}
    # The call id the HARNESS uses is not available here and must not be: this server knows the
    # call by the JSON-RPC id it arrived with, which is its own, native knowledge. The comparator
    # joins on destination host, not on this string.
    call_id = f"rpc{mid}"
    slot = int(args.get("slot", 0))
    fragment = str(args.get("fragment", ""))
    channel = str(args.get("channel", "none"))

    try:
        if name == "bench_emit":
            _egress(call_id, slot, fragment, channel, args)
        elif name == "bench_emit_many":
            for i in range(int(args.get("count", 1))):
                _egress(call_id, slot, fragment, channel, args)
        elif name == "bench_emit_late":
            delay = int(args.get("delay_ms", 1500)) / 1000.0
            _send({"jsonrpc": "2.0", "id": mid,
                   "result": {"content": [{"type": "text", "text": "answered, egress pending"}],
                              "isError": False}})
            # Deliberately AFTER the response: the point of this tool is egress that no time
            # window around the call can contain.
            threading.Thread(target=lambda: (time.sleep(delay),
                                             _egress(call_id, slot, fragment, channel, args)),
                             daemon=True).start()
            return
        elif name == "bench_emit_encoded":
            encoding = str(args.get("encoding", "base64"))
            payload = _encode(fragment, encoding)
            host = _sink_host(slot)
            url = _sink_url(slot, "/bench/encoded")
            req = urllib.request.Request(url, data=payload, method="POST",
                                         headers={"content-type": "application/octet-stream"})
            error = ""
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    resp.read()
            except (urllib.error.URLError, OSError, socket.timeout) as exc:
                error = f"{type(exc).__name__}: {exc}"
            _truth({"call_id": call_id, "dest_host": host, "path": "/bench/encoded",
                    "method": "POST", "channel": f"body:{encoding}", "fragment": fragment,
                    "ts": time.time(), "error": error, "request_target": "/bench/encoded",
                    "request_body_b64": base64.b64encode(payload).decode(),
                    "call_arguments": args})
        else:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32602, "message": f"Unknown tool: {name}",
                             "data": {"available": sorted(TOOL_NAMES)}}})
            return
    except Exception as exc:  # a bench failure is data: report it as a tool error, do not die
        _send({"jsonrpc": "2.0", "id": mid,
               "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"}})
        return

    _send({"jsonrpc": "2.0", "id": mid,
           "result": {"content": [{"type": "text", "text": "ok"}], "isError": False}})


def main() -> int:
    global _truth_path
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=os.environ.get("BENCH_TRUTH", ""),
                    help="path for this server's own ledger of what it sent")
    args = ap.parse_args()
    _truth_path = args.truth

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid = msg.get("method"), msg.get("id")

        if mid is None:
            continue  # notifications/initialized and friends: nothing to answer
        if method == "initialize":
            asked = (msg.get("params") or {}).get("protocolVersion")
            if asked != PROTOCOL_VERSION:
                _send({"jsonrpc": "2.0", "id": mid,
                       "error": {"code": -32602,
                                 "message": f"unsupported protocolVersion {asked}",
                                 "data": {"supported": [PROTOCOL_VERSION]}}})
                continue
            _send({"jsonrpc": "2.0", "id": mid,
                   "result": {"protocolVersion": PROTOCOL_VERSION,
                              "capabilities": {"tools": {}},
                              "serverInfo": {"name": "mcp-fanout-bench", "version": "1"}}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            # Own thread per call, so concurrent calls genuinely overlap on the wire. Without
            # this the wave would serialize and every window would look like one call.
            threading.Thread(target=_handle_call, args=(mid, msg.get("params") or {}),
                             daemon=True).start()
        else:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": "method not found"}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
