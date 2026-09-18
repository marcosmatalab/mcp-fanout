"""mitmproxy addon: turn each intercepted outbound request into a redacted Flow record.

Why mitmproxy (a terminating proxy) and not eBPF for the MEASUREMENT: to read the plaintext of
an HTTPS body we must terminate the TLS. A local proxy with a CA in the container trust store
does that with one dependency and no kernel privileges, which is the right cost for a one
afternoon measurement. eBPF uprobes on SSL_write/SSL_read (docs/METHOD.md) are the product-grade
path: they also catch certificate-pinned clients and non-proxied flows, at the cost of being
Linux and kernel specific. The measurement accepts the proxy's blind spots and reports them
(a pinned or non-HTTP flow is counted by the pcap backstop in harness/run.sh and marked
INDETERMINADO for content).

This addon runs inside mitmdump's process. It never stores a captured byte: it hashes the body
in memory, keeps counts and a state, and writes one Flow line. Configuration comes from the
environment so the same addon serves a reproducible measurement (fixed salt) and a real
deployment (secret salt) without code changes.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import match as _match
from .classify import classify_host
from .record import Flow, write_jsonl
from .redact import Redactor


class FanoutRecorder:
    def __init__(self) -> None:
        self.run_dir = Path(os.environ.get("MCPFANOUT_RUNDIR", "runs/live"))
        self.run_id = os.environ.get("MCPFANOUT_RUNID", "live")
        salt = os.environ.get("MCPFANOUT_SALT", "").encode() or None
        k = int(os.environ.get("MCPFANOUT_K", "16"))
        w = int(os.environ.get("MCPFANOUT_W", "8"))
        self.redactor = Redactor(salt=salt, k=k, w=w) if salt else Redactor(k=k, w=w)
        self.control = Path(os.environ.get("MCPFANOUT_CONTROL", "runs/live/control"))
        self.flows_path = self.run_dir / "flows.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Context is provided pre-digested (content-free) as {ref: [digest, ...]}.
        ctx_path = os.environ.get("MCPFANOUT_CONTEXT", "")
        self.context_index: dict[str, frozenset[str]] = {}
        if ctx_path and Path(ctx_path).exists():
            raw = json.loads(Path(ctx_path).read_text(encoding="utf-8"))
            self.context_index = {ref: frozenset(digs) for ref, digs in raw.items()}

        self._buffer: list[Flow] = []

    def _current_call(self) -> dict:
        """Read the active call published by the driver. Empty dict if none is active yet."""
        p = self.control / "current_call.json"
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A torn read is treated as "no active call": attribute nothing rather than guess.
            return {}

    # mitmproxy hook. Named exactly as mitmproxy expects.
    def request(self, flow) -> None:  # type: ignore[no-untyped-def]
        req = flow.request
        body = req.raw_content or b""
        current = self._current_call()
        args_digests = frozenset(current.get("args_digests", []))

        result = _match.match_body(body, self.context_index, args_digests, self.redactor)

        tp = current.get("traceparent", "")
        header_tp = req.headers.get("traceparent", "")
        our_tp_present = bool(tp) and (tp == header_tp or (body and tp.encode() in body))

        state = _match.decide_state(result.causal, body_observed=True, has_time_and_pid=True)

        try:
            dest_ip = flow.server_conn.peername[0] if flow.server_conn.peername else ""
        except Exception:
            dest_ip = ""

        self._buffer.append(Flow(
            run_id=self.run_id, server_id=current.get("server_id", ""),
            call_id=current.get("call_id"), ts=time.time(),
            dest_host=req.pretty_host, dest_ip=dest_ip, scheme=req.scheme, method=req.method,
            request_size=len(body), body_observed=True, our_traceparent_present=our_tp_present,
            total_bytes=result.total_bytes, matched_bytes=result.matched_bytes,
            matched_refs=result.matched_refs, causal=result.causal, state=state,
            node_category=classify_host(req.pretty_host), has_time_and_pid=True,
        ))

    def done(self) -> None:
        """Flush buffered flows when mitmdump shuts down. Append so multiple servers accumulate."""
        existing = []
        if self.flows_path.exists():
            existing = self.flows_path.read_text(encoding="utf-8").splitlines()
        # Rewrite existing + new so the file stays valid JSONL even across addon restarts.
        with self.flows_path.open("a", encoding="utf-8") as _:
            pass
        write_jsonl(self.flows_path.with_suffix(".tmp"), self._buffer)
        new_lines = self.flows_path.with_suffix(".tmp").read_text(encoding="utf-8").splitlines()
        self.flows_path.write_text("\n".join([*existing, *new_lines]) + ("\n" if existing or new_lines else ""),
                                   encoding="utf-8")
        self.flows_path.with_suffix(".tmp").unlink(missing_ok=True)


addons = [FanoutRecorder()]
