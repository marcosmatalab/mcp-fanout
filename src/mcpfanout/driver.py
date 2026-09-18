"""MCP stdio driver: speaks JSON-RPC to a server and drives a fixed call corpus.

This is the "agent" side, minus the LLM. We do not need a model to make an MCP server call a
third party: we speak the protocol directly and send a fixed, deterministic corpus of tool
calls. Determinism here is a requirement, not a convenience: a reproducible measurement cannot
depend on what a model decided to do this time (docs/THE-GATE.md rule 1).

Protocol revisions. Three separate claims, three separate sources; conflating them is how the
constant below came to disagree with the wire for a whole release.

1. THE WIRE WE IMPLEMENT IS 2025-11-25. That is a handshake protocol: initialize, then
   notifications/initialized, then tools/list and tools/call. PROTOCOL_VERSION below says so.
   We deliberately do NOT implement 2026-07-28, which removed that handshake: there, every
   request carries its own io.modelcontextprotocol/protocolVersion in _meta and servers MUST
   implement a server/discover RPC (SEP-2575, major changes 2 and 3 of
   https://modelcontextprotocol.io/specification/2026-07-28/changelog). Sending an initialize
   that announces 2026-07-28 is self-contradictory, because under 2026-07-28 initialize does
   not exist. Speaking the newer revision is a rewrite, not a constant; it is backlog.

2. THE TRACE-CONTEXT CONVENTION IS DOCUMENTED IN 2026-07-28, BY SEP-414. The keys traceparent,
   tracestate and baggage ride in _meta unprefixed (an explicit exception to the reverse-DNS
   rule for _meta keys, so that existing OpenTelemetry tooling keeps working) and carry W3C
   Trace Context values. SEP-414 is Final: https://modelcontextprotocol.io/seps/414-request-meta
   and it is minor change 2 of the changelog cited above.

3. SETTING _meta.traceparent WHILE SPEAKING 2025-11-25 IS VALID, though it is ahead of the
   revision that documents it. _meta is an open extension field in both revisions, so the key
   is carried by a field built to carry it, not smuggled through one that was not. Nor is it an
   injection under negativa 1 (docs/DOCTRINE.md): the request is one we make to a server we
   ourselves launched, on our own machine. We plant nothing in a third party. If the server
   forwards the header downstream that is the server's own choice, and observing that choice is
   precisely number 3. The capture layer then sees our own traceparent in the outbound request,
   which also attributes that connection to this exact call.

Transport: MCP stdio is newline-delimited JSON-RPC 2.0 (one JSON object per line). We implement
just enough of it: initialize, initialized, tools/list, tools/call. No streaming, no batching;
the corpus is sequential so we never need concurrent requests.
"""

from __future__ import annotations

import json
import os
import queue
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass

# The revision whose wire format this module actually speaks. Claim 1 of the module docstring.
# Rejected: "2026-07-28", the current revision. It is the newest and it is where SEP-414 went
# Final, which is why it was picked, but it deleted the initialize handshake this driver is built
# on, so announcing it inside an initialize describes a protocol neither side is speaking.
PROTOCOL_VERSION = "2025-11-25"

# How long one request may wait for its response before we call the server hung. A read that is
# not bounded is not a timeout "owned by the run loop", it is a harness that hangs forever on a
# server that starts and says nothing. Rejected: select() on the pipe, which fights text-mode
# buffering; a reader thread plus a queue cannot disagree with the buffer about what has arrived.
DEFAULT_READ_TIMEOUT_S = 20.0


class ServerTimeout(Exception):
    """A server accepted a request and did not answer inside its budget.

    Its own type, not a bare RuntimeError: "answered with an error" and "never answered" are
    different observations, and the registry has to be able to tell them apart.
    """


def new_traceparent() -> str:
    """A fresh W3C traceparent: version 00, random 16-byte trace id, 8-byte span id, sampled."""
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    return f"00-{trace_id}-{span_id}-01"


@dataclass
class CallSpec:
    """One entry of the corpus: which tool, with which arguments."""
    tool_name: str
    arguments: dict


@dataclass
class DriveResult:
    call_id: str
    tool_name: str
    args_present: bool
    traceparent: str
    ok: bool
    error: str = ""


class StdioMCPClient:
    """Minimal MCP client over a server subprocess's stdio.

    Error handling is deliberate: a server that hangs must not hang the harness, so every
    request is bounded by ``read_timeout`` and a breach raises ServerTimeout, which the run loop
    records as a failed call rather than dying on. A malformed line is surfaced, not swallowed,
    because silent tolerance would let a broken server produce an empty, falsely clean
    measurement.
    """

    def __init__(self, command: list[str], env: dict | None = None, *,
                 read_timeout: float = DEFAULT_READ_TIMEOUT_S) -> None:
        self.command = command
        self.env = {**os.environ, **(env or {})}
        self.read_timeout = read_timeout
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._stderr_tail: list[str] = []
        # Lines arrive on a reader thread so no read can block the harness indefinitely.
        self._stdout_q: "queue.Queue[str | None]" = queue.Queue()

    def __enter__(self) -> "StdioMCPClient":
        self.proc = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=self.env, bufsize=1, text=True,
        )
        # Drain stderr on a thread so a chatty server cannot deadlock on a full pipe.
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        # Read stdout on a thread too, so _read can wait with a deadline instead of blocking in
        # readline(). Both are daemons: __exit__ kills the process, which unblocks them.
        threading.Thread(target=self._drain_stdout, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _drain_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self._stdout_q.put(line)
        self._stdout_q.put(None)  # sentinel: the server closed stdout

    def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            # Keep only the last few lines; server stderr is diagnostic, not measurement data.
            self._stderr_tail.append(line.rstrip())
            del self._stderr_tail[:-20]

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, obj: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _read(self, deadline: float) -> dict:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ServerTimeout(f"no response within {self.read_timeout}s. "
                                f"stderr tail: {self._stderr_tail[-5:]}")
        try:
            line = self._stdout_q.get(timeout=remaining)
        except queue.Empty:
            raise ServerTimeout(f"no response within {self.read_timeout}s. "
                                f"stderr tail: {self._stderr_tail[-5:]}") from None
        if line is None:
            raise EOFError(f"server closed stdout. stderr tail: {self._stderr_tail[-5:]}")
        return json.loads(line)

    def request(self, method: str, params: dict | None = None,
                *, timeout: float | None = None) -> dict:
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        # One budget for the whole request, not one per read: a server that emits an unrelated
        # notification just inside every per-read window would otherwise stall us forever while
        # looking responsive. Rejected: per-read timeout, for exactly that reason.
        deadline = time.monotonic() + (self.read_timeout if timeout is None else timeout)
        # Read until we get the response with our id, skipping any server-initiated notifications.
        while True:
            msg = self._read(deadline)
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(f"{method} error: {msg['error']}")
                return msg.get("result", {})

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self, *, timeout: float | None = None) -> dict:
        # Separate budget on purpose: with npx/uvx the package download runs inside our own
        # subprocess, so the first response can be a cold minute away while every later one is
        # milliseconds. One shared timeout would have to be the slow one, which would mean a
        # hung tools/call is not noticed for a minute.
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-fanout", "version": "0.1.0"},
        }, timeout=timeout)
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict]:
        return self.request("tools/list").get("tools", [])

    def call_tool(self, spec: CallSpec, traceparent: str) -> dict:
        # SEP-414: trace context rides in params._meta. This is the reserved field, not a payload
        # we smuggle into a third party.
        return self.request("tools/call", {
            "name": spec.tool_name,
            "arguments": spec.arguments,
            "_meta": {"traceparent": traceparent},
        })


def _write_current(control_dir, payload: dict) -> None:
    """Atomically publish the currently active call so the capture addon can attribute egress.

    The corpus is driven sequentially, one call at a time per server, so at any instant there is
    exactly one active call. Writing it here gives the addon ground-truth attribution without a
    time-window guess. Atomic write (temp + rename) so the addon never reads a half-written file.
    """
    import json as _json
    import os as _os
    from pathlib import Path as _Path
    control_dir = _Path(control_dir)
    control_dir.mkdir(parents=True, exist_ok=True)
    tmp = control_dir / "current_call.json.tmp"
    tmp.write_text(_json.dumps(payload), encoding="utf-8")
    _os.replace(tmp, control_dir / "current_call.json")


def drive(command: list[str], corpus: list[CallSpec], run_id: str, server_id: str,
          env: dict | None = None, *, redactor=None, control_dir=None,
          calls_path=None) -> list[DriveResult]:
    """Run the handshake and the corpus against one server, returning the driven calls.

    When ``control_dir`` and ``redactor`` are given, the driver publishes the active call (with
    its argument digests) before each call, which is how the capture addon attributes and matches
    without ever seeing raw arguments. When ``calls_path`` is given, each ToolCall is appended to
    calls.jsonl. With none of these, the driver is pure (used by the unit test).
    """
    from .record import ToolCall, write_jsonl  # local import: record is core, avoids a cycle at import time

    results: list[DriveResult] = []
    tool_calls = []
    with StdioMCPClient(command, env) as client:
        client.initialize()
        client.list_tools()  # listed for realism and to let servers lazily wire up tools
        for i, spec in enumerate(corpus):
            tp = new_traceparent()
            call_id = f"{server_id}-c{i:03d}"
            args_present = bool(spec.arguments)

            if control_dir is not None and redactor is not None:
                args_bytes = json.dumps(spec.arguments, sort_keys=True).encode() if args_present else b""
                args_digests = sorted(redactor.kgram_digest_set(args_bytes)) if args_present else []
                _write_current(control_dir, {
                    "run_id": run_id, "server_id": server_id, "call_id": call_id,
                    "traceparent": tp, "args_present": args_present, "args_digests": args_digests,
                })

            try:
                client.call_tool(spec, tp)
                ok, err = True, ""
            except Exception as exc:  # a failing call is data, not a crash: record and continue
                ok, err = False, str(exc)

            results.append(DriveResult(call_id=call_id, tool_name=spec.tool_name,
                                       args_present=args_present, traceparent=tp, ok=ok, error=err))
            tool_calls.append(ToolCall(run_id, server_id, call_id, spec.tool_name, args_present, tp))

    if calls_path is not None:
        write_jsonl(calls_path, tool_calls)
    return results
