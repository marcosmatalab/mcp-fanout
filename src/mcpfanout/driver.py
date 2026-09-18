"""MCP stdio driver: speaks JSON-RPC to a server and drives a fixed call corpus.

This is the "agent" side, minus the LLM. We do not need a model to make an MCP server call a
third party: we speak the protocol directly and send a fixed, deterministic corpus of tool
calls. Determinism here is a requirement, not a convenience: a reproducible measurement cannot
depend on what a model decided to do this time (docs/THE-GATE.md rule 1).

We set a W3C traceparent in params._meta of every tools/call. Per SEP-414 (MCP spec, Final,
2026-07-28) this is where trace context belongs; it is NOT an injection into a third party, it
is a field the standard reserves. If the server propagates it downstream, the capture layer
sees our own traceparent in the outbound request, which both attributes the connection to this
exact call and answers number 3 (does the server propagate?).

Transport: MCP stdio is newline-delimited JSON-RPC 2.0 (one JSON object per line). We implement
just enough of it: initialize, initialized, tools/list, tools/call. No streaming, no batching;
the corpus is sequential so we never need concurrent requests.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
from dataclasses import dataclass

PROTOCOL_VERSION = "2026-07-28"  # the spec revision that made SEP-414 Final (see module docstring)


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

    Error handling is deliberate: a server that hangs must not hang the harness, so every read
    is bounded by a timeout enforced by the caller (we read line by line and the run loop owns
    the wall clock). A malformed line is surfaced, not swallowed, because silent tolerance would
    let a broken server produce an empty, falsely clean measurement.
    """

    def __init__(self, command: list[str], env: dict | None = None) -> None:
        self.command = command
        self.env = {**os.environ, **(env or {})}
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._stderr_tail: list[str] = []

    def __enter__(self) -> "StdioMCPClient":
        self.proc = subprocess.Popen(
            self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=self.env, bufsize=1, text=True,
        )
        # Drain stderr on a thread so a chatty server cannot deadlock on a full pipe.
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

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

    def _read(self) -> dict:
        assert self.proc and self.proc.stdout
        line = self.proc.stdout.readline()
        if not line:
            raise EOFError(f"server closed stdout. stderr tail: {self._stderr_tail[-5:]}")
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        # Read until we get the response with our id, skipping any server-initiated notifications.
        while True:
            msg = self._read()
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(f"{method} error: {msg['error']}")
                return msg.get("result", {})

    def notify(self, method: str, params: dict | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self) -> dict:
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-fanout", "version": "0.1.0"},
        })
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
