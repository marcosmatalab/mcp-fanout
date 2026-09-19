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

from .record import PHASE_DRAINED, PHASE_DRIVING, PHASE_HANDSHAKE, PHASE_LAUNCHER

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
    stdout_noise_lines: int = 0   # non-JSON-RPC lines the server wrote to stdout; see _read()


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
        # Non-JSON-RPC lines seen on stdout. See _read().
        self.stdout_noise_lines = 0
        self._noise_tail: list[str] = []
        # Responses that arrived while we were waiting for a different id. Needed the moment
        # more than one request is in flight: without it, await_response would DISCARD another
        # call's answer while looking for its own, and concurrent driving would hang on the
        # calls whose responses were thrown away.
        self._pending: dict[int, dict] = {}

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
        """Read the next JSON-RPC message, skipping lines that are not one.

        MCP stdio reserves stdout for the protocol and directs logging to stderr, but real
        servers break that. mcp-server-fetch 2026.8.18 shells out to npm during a tools/call and
        lets npm write to its own stdout, so the JSON-RPC channel carries lines like "added 41
        packages, and audited 42 packages in 4s" and bare newlines. Parsing every line made
        every call to that server fail with "Expecting value: line 2 column 1".

        So non-JSON lines are skipped AND COUNTED, which is the point. The previous behaviour of
        raising was chosen to stop a broken server producing a falsely clean measurement, and
        that concern is right; silently swallowing the noise would have the same fault in the
        other direction. Counting keeps the concern and drops the crash: the count rides out in
        the ToolCall record, so "this server corrupts its own protocol channel" is reported as a
        property of the server instead of losing us the measurement entirely.
        """
        while True:
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
            if not line.strip():
                self.stdout_noise_lines += 1
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                self.stdout_noise_lines += 1
                self._noise_tail.append(line.rstrip()[:200])
                del self._noise_tail[:-10]
                continue

    def send_request(self, method: str, params: dict | None = None) -> int:
        """Send a request WITHOUT waiting, returning its JSON-RPC id.

        Split out from request() so several calls can be in flight at once, which is the whole
        point of the phase A bench: CONTENT_UNIQUE is unreachable unless more than one call is
        active, so a client that can only do one at a time cannot measure the project's thesis.
        """
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        return rid

    def await_response(self, rid: int, *, method: str = "", timeout: float | None = None) -> dict:
        """Wait for one id's response, stashing any other response that arrives first.

        Stashing rather than skipping is the correctness requirement under concurrency. Server
        notifications have no id and are dropped; another request's response is kept.
        """
        if rid in self._pending:
            msg = self._pending.pop(rid)
            if "error" in msg:
                raise RuntimeError(f"{method or 'request'} error: {msg['error']}")
            return msg.get("result", {})
        # One budget for the whole wait, not one per read: a server that emits an unrelated
        # notification just inside every per-read window would otherwise stall us forever while
        # looking responsive. Rejected: per-read timeout, for exactly that reason.
        deadline = time.monotonic() + (self.read_timeout if timeout is None else timeout)
        while True:
            msg = self._read(deadline)
            mid = msg.get("id")
            if mid is None:
                continue  # a server-initiated notification: not a response to anything of ours
            if mid != rid:
                self._pending[mid] = msg
                continue
            if "error" in msg:
                raise RuntimeError(f"{method or 'request'} error: {msg['error']}")
            return msg.get("result", {})

    def request(self, method: str, params: dict | None = None,
                *, timeout: float | None = None) -> dict:
        rid = self.send_request(method, params)
        return self.await_response(rid, method=method, timeout=timeout)

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


def _write_active_calls(control_dir, payload: dict) -> None:
    """Atomically publish the set of IN-FLIGHT calls so the addon can attribute egress.

    A LIST, not a single call, and the name says so. Today the corpus is driven sequentially so
    the list always holds exactly one entry, which is why the previous version wrote
    "current_call.json" and a scalar. That shape made the tautology in
    match.grade_attribution unfalsifiable: with no way to record how many calls were in flight,
    every content match looked uncontested and looked unique at the same time. Publishing the
    list means phase C (concurrent calls) is a change to the driver's loop and to this payload,
    not a change to the evidence model or the addon.

    Atomic write (temp + rename) so the addon never reads a half-written file.
    """
    import json as _json
    import os as _os
    from pathlib import Path as _Path
    control_dir = _Path(control_dir)
    control_dir.mkdir(parents=True, exist_ok=True)
    tmp = control_dir / "active_calls.json.tmp"
    tmp.write_text(_json.dumps(payload), encoding="utf-8")
    _os.replace(tmp, control_dir / "active_calls.json")


def args_bytes(arguments: dict) -> bytes:
    """The exact bytes a call's arguments are matched as. ONE definition, on purpose.

    Sorted keys so two runs over the same call produce the same digests (gate rule 1). Exposed
    because the calibration measurement (mcpfanout.calibrate) has to ask the matcher the same
    question the capture addon asks, and two places serialising arguments their own way is how a
    published false-positive rate comes to describe a matcher nobody ships.
    """
    return json.dumps(arguments, sort_keys=True).encode()


def args_digests_for(spec: CallSpec, redactor) -> list[str]:
    """The sorted digest set of one call's arguments, or empty when it carries none."""
    if not spec.arguments:
        return []
    return sorted(redactor.kgram_digest_set(args_bytes(spec.arguments)))


def publish_active_calls(control_dir, run_id: str, server_id: str,
                         entries: list[dict], phase: str = "") -> None:
    """Publish the in-flight set the capture addon reads. Pass [] to declare none in flight.

    Exposed so the phase A bench driver publishes through the same function the sequential
    driver uses. Two writers of the same file with two notions of its shape is how the addon
    ends up reading a payload nobody wrote.

    ``phase`` says where in the server's lifecycle we are (record.PHASES_LIFECYCLE). It is
    published alongside the in-flight set rather than derived from it, because "no call is in
    flight" has several meanings and they are not equivalent: the launcher is still downloading the
    package and the server does not exist; the process exists and is handshaking; a call just
    returned and the next has not been sent. Only the first makes a flow impossible to attribute to
    a call BY CONSTRUCTION, and the addon cannot tell them apart from an empty list.
    """
    _write_active_calls(control_dir, {"run_id": run_id, "server_id": server_id,
                                      "active_calls": entries, "phase": phase})


def drive_wave(client: "StdioMCPClient", specs: list[CallSpec], run_id: str, server_id: str,
               *, redactor, control_dir, start_index: int = 0,
               timeout: float | None = None) -> list[DriveResult]:
    """Drive several calls CONCURRENTLY over one connection, as a single wave.

    The wave is the unit that makes attribution measurable. All of the wave's calls are
    published as in flight BEFORE any of them is sent, so the addon sees a window of N and can
    grade CONTENT_UNIQUE (N > 1 and the fragment in exactly one) apart from
    CONTENT_AMBIGUOUS (in several). Then all requests are sent, then all responses collected.

    The in-flight set is cleared after the wave, deliberately. Egress that arrives afterwards is
    then unattributed, which is the correct answer and is exactly what the bench's
    "task still alive after the response" case exists to demonstrate: a time window cannot
    attribute what happens outside it.
    """
    entries = []
    for i, spec in enumerate(specs):
        entries.append({
            "call_id": f"{server_id}-c{start_index + i:03d}",
            "traceparent": new_traceparent(),
            "args_present": bool(spec.arguments),
            "args_digests": args_digests_for(spec, redactor),
        })
    publish_active_calls(control_dir, run_id, server_id, entries, phase=PHASE_DRIVING)

    rids = []
    for spec, entry in zip(specs, entries):
        rids.append(client.send_request("tools/call", {
            "name": spec.tool_name, "arguments": spec.arguments,
            "_meta": {"traceparent": entry["traceparent"]},
        }))

    results = []
    for spec, entry, rid in zip(specs, entries, rids):
        try:
            client.await_response(rid, method="tools/call", timeout=timeout)
            ok, err = True, ""
        except Exception as exc:  # a failing call is data, not a crash
            ok, err = False, f"{type(exc).__name__}: {exc}"
        results.append(DriveResult(
            call_id=entry["call_id"], tool_name=spec.tool_name,
            args_present=entry["args_present"], traceparent=entry["traceparent"],
            ok=ok, error=err, stdout_noise_lines=0))

    publish_active_calls(control_dir, run_id, server_id, [], phase=PHASE_DRAINED)
    return results


def drive(command: list[str], corpus: list[CallSpec], run_id: str, server_id: str,
          env: dict | None = None, *, redactor=None, control_dir=None,
          calls_path=None) -> list[DriveResult]:
    """Run the handshake and the corpus against one server, returning the driven calls.

    When ``control_dir`` and ``redactor`` are given, the driver publishes the active call (with
    its argument digests) before each call, which is how the capture addon attributes and matches
    without ever seeing raw arguments. When ``calls_path`` is given, each ToolCall is appended to
    calls.jsonl. With none of these, the driver is pure (used by the unit test).

    A SERVER THAT CANNOT START IS A DATA POINT, NOT A STOP, and it took a ten-server capture to
    notice this function did not implement that. Per-call failures were already recorded and
    survived, but ``initialize`` and ``list_tools`` sat outside every try, so one server exiting
    before the handshake (mcp-server-git, with no git binary in the image) raised out of here,
    through drive_all, and ended the whole run after two servers. The nine that worked were lost
    to the one that did not. Now a startup failure records every call of that server's corpus as
    not driven, with the reason, and the run continues: "this server did not start" is exactly the
    kind of finding the registry exists to hold.
    """
    from .record import ToolCall, write_jsonl  # local import: record is core, avoids a cycle at import time

    results: list[DriveResult] = []
    tool_calls = []
    try:
        _drive_corpus(command, corpus, run_id, server_id, env, redactor=redactor,
                      control_dir=control_dir, results=results, tool_calls=tool_calls)
    except Exception as exc:
        # Startup, teardown, or a failure that killed the connection mid-corpus. Whatever was
        # already driven is kept; the rest is recorded as not driven, once each, with the reason.
        err = f"{type(exc).__name__}: {exc}"
        for i, spec in enumerate(corpus):
            call_id = f"{server_id}-c{i:03d}"
            if any(r.call_id == call_id for r in results):
                continue
            results.append(DriveResult(call_id=call_id, tool_name=spec.tool_name,
                                       args_present=bool(spec.arguments), traceparent="",
                                       ok=False, error=err))
            tool_calls.append(ToolCall(run_id, server_id, call_id, spec.tool_name,
                                       bool(spec.arguments), "", ok=False, error=err,
                                       wave_size=1))

    if calls_path is not None:
        write_jsonl(calls_path, tool_calls)
    return results


def _drive_corpus(command, corpus, run_id, server_id, env, *, redactor, control_dir,
                  results, tool_calls) -> None:
    """The driving loop itself, so ``drive`` can wrap it whole. Appends to the caller's lists.

    Split out rather than nested in a try inside drive() so that the two concerns stay legible:
    this function drives, and drive() decides what an escaped exception means for the record.
    """
    from .record import ToolCall

    published = control_dir is not None and redactor is not None
    if published:
        # BEFORE the subprocess exists. `npx -y pkg@ver` and `uvx pkg@ver` resolve and may download
        # the package before the server's first instruction runs, and that egress is the launcher's,
        # not the server's. Publishing this phase first is what makes it impossible to attribute to
        # a call of ours, whatever a time window would have said.
        publish_active_calls(control_dir, run_id, server_id, [], phase=PHASE_LAUNCHER)

    with StdioMCPClient(command, env) as client:
        if published:
            publish_active_calls(control_dir, run_id, server_id, [], phase=PHASE_HANDSHAKE)
        client.initialize()
        client.list_tools()  # listed for realism and to let servers lazily wire up tools
        for i, spec in enumerate(corpus):
            tp = new_traceparent()
            call_id = f"{server_id}-c{i:03d}"
            args_present = bool(spec.arguments)

            if published:
                # One entry, because this path is sequential. drive_wave publishes several.
                publish_active_calls(control_dir, run_id, server_id, [{
                    "call_id": call_id, "traceparent": tp, "args_present": args_present,
                    "args_digests": args_digests_for(spec, redactor),
                }], phase=PHASE_DRIVING)

            noise_before = client.stdout_noise_lines
            try:
                client.call_tool(spec, tp)
                ok, err = True, ""
            except Exception as exc:  # a failing call is data, not a crash: record and continue
                ok, err = False, f"{type(exc).__name__}: {exc}"

            noise = client.stdout_noise_lines - noise_before
            results.append(DriveResult(call_id=call_id, tool_name=spec.tool_name,
                                       args_present=args_present, traceparent=tp, ok=ok,
                                       error=err, stdout_noise_lines=noise))
            tool_calls.append(ToolCall(run_id, server_id, call_id, spec.tool_name, args_present,
                                       tp, ok=ok, error=err, stdout_noise_lines=noise,
                                       wave_size=1))

            if published:
                # DRAIN AFTER EVERY CALL, not only at the end of the corpus. Leaving the call
                # published until the next one is sent credits whatever arrives in between to a call
                # that has already returned, which is how the next server's launcher traffic ended
                # up pinned to the previous server's last call in the first ten-server capture.
                # drive_wave has always drained; this path had not, and the asymmetry WAS the
                # defect. The cost is deliberate and is the one the bench's late_egress cell
                # demonstrates: egress a server makes just after its response now comes out
                # unattributed, which is the honest answer rather than the flattering one.
                publish_active_calls(control_dir, run_id, server_id, [], phase=PHASE_DRAINED)
