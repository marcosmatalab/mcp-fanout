"""mitmproxy addon: turn each intercepted outbound request into a redacted Flow record.

Why mitmproxy (a terminating proxy) and not eBPF for the MEASUREMENT: to read the plaintext of
an HTTPS body we must terminate the TLS. A local proxy with a CA in the container trust store
does that with one dependency and no kernel privileges, which is the right cost for a one
afternoon measurement. eBPF uprobes on SSL_write/SSL_read (docs/METHOD.md) are the product-grade
path: they also catch certificate-pinned clients and non-proxied flows, at the cost of being
Linux and kernel specific. The measurement accepts the proxy's blind spots and reports them
(a pinned or non-HTTP flow is counted by the pcap backstop in harness/run.sh and recorded with
occurrence connection_only and provenance unknown).

This addon runs inside mitmdump's process. It never stores a captured byte: it hashes the body
in memory, keeps counts and a state, and writes one Flow line. Configuration comes from the
environment so the same addon serves a reproducible measurement (fixed salt) and a real
deployment (secret salt) without code changes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Absolute imports, deliberately, even though this file lives inside the package. mitmproxy
# loads an addon BY PATH under a synthetic package name ("__mitmproxy_script__.capture_addon")
# that does not exist, so a relative import raises ModuleNotFoundError and the addon never
# loads -- silently, because mitmdump logs it and carries on proxying, producing a run with zero
# flows that looks like a server that never egressed. tests/test_capture_addon_loads.py loads
# this file the way mitmproxy does, so the mistake cannot come back.
from mcpfanout import match as _match
from mcpfanout import shingle as _shingle
from mcpfanout import structure as _structure
from mcpfanout.classify import ConstantPathList, classify_host
from mcpfanout.record import Flow
from mcpfanout.redact import Redactor


def _our_traceparent_present(tp: str, header_tp: str, body: bytes) -> bool:
    """Did OUR traceparent appear in this outbound request, in the header or in the body?

    Each clause is forced to bool separately, and the short form is rejected on evidence. Written
    as `bool(tp) and (tp == header_tp or (body and tp.encode() in body))` this silently produced
    b"" instead of False: with an active call, an empty body and no traceparent header,
    `body and ...` short-circuits to b"", `or` propagates it and `and` returns it. A bytes value
    in a bool field then made json.dumps raise inside done(), which discarded every buffered flow
    in the run: the whole capture, lost to a GET with no body.
    tests/test_capture_addon_hooks.py pins this exact case.
    """
    in_header = bool(tp) and tp == header_tp
    in_body = bool(tp) and bool(body) and tp.encode() in body
    return in_header or in_body


def _attributed_call(active: list[dict[str, Any]], matching: list[dict[str, Any]],
                     cand: Any) -> dict[str, Any]:
    """Which in-flight call this request is recorded against, or {} for none.

    Structural evidence first, because it is the instrument number 5 is published from; the
    k-gram result stays in the record for number 4 and never attributes. Then the single active
    call if there is only one. Never "whichever ran last", and NEVER a call the discrimination
    rule just rejected: a flow whose only contained call was excluded for owning no
    distinguishing token goes out unattributed and is not handed back to that call by a fallback.
    That reassignment is the tempting bug, it would undo exactly what the rule bought, and
    tests/test_structural_attribution.py pins it.
    """
    if len(cand.discriminating) == 1:
        chosen: dict[str, Any] = active[cand.discriminating[0]]
        return chosen
    if cand.contained and not cand.discriminating:
        return {}
    if len(matching) == 1:
        return matching[0]
    if len(active) == 1 and not cand.contained:
        return active[0]
    return {}


class FanoutRecorder:
    def __init__(self) -> None:
        self.run_dir = Path(os.environ.get("MCPFANOUT_RUNDIR", "runs/live"))
        self.run_id = os.environ.get("MCPFANOUT_RUNID", "live")
        salt = os.environ.get("MCPFANOUT_SALT", "").encode() or None
        # Defaults from the shipped constants, never literals. This module carried its own "16"
        # and "8", and when k was chosen by measurement (docs/CALIBRATION.md, F1.2) the addon kept
        # matching at the old value: a capture would have graded at a k no published figure
        # describes, silently, because a k mismatch does not error, it just stops matching.
        # tests/test_capture_addon_hooks.py caught it as a flow that carried the fixture's own
        # token and came out non-causal.
        k = int(os.environ.get("MCPFANOUT_K", str(_shingle.DEFAULT_K)))
        w = int(os.environ.get("MCPFANOUT_W", str(_shingle.DEFAULT_W)))
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

        # The declared list of client-constant targets, loaded once. Absent means the flag is
        # never set, which counts every flow into the content denominator: the conservative
        # direction, and it is reported by the aggregate rather than assumed.
        self.constant_paths = ConstantPathList.load(
            os.environ.get("MCPFANOUT_CONSTANT_PATHS", "registry/client-constant-paths.json"))

        self._buffer: list[Flow] = []

    def _active_calls(self) -> dict[str, Any]:
        """Read the in-flight calls published by the driver. Empty dict if none are active yet."""
        p = self.control / "active_calls.json"
        if not p.exists():
            return {}
        try:
            published: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
            return published
        except (json.JSONDecodeError, OSError):
            # A torn read is treated as "no active calls": attribute nothing rather than guess.
            return {}

    def _calls_whose_own_arguments_matched(self, active: list[dict[str, Any]], result: Any,
                                           target: bytes, body: bytes) -> list[dict[str, Any]]:
        """Of the in-flight calls, which ones individually contain the matched fragment.

        The union answers "was any of our argument material in this request"; this per-call count
        is what tells CONTENT_UNIQUE (one candidate of several) from CONTENT_AMBIGUOUS (several)
        and from CONTENT_MATCH_UNCONTESTED (only one candidate existed). Without the second number
        the strongest grade would be unearnable and unfalsifiable at once.
        """
        if not result.causal:
            return []
        matching = []
        for call in active:
            per_call = frozenset(call.get("args_digests", []))
            if per_call and _match.match_request(target, body, {}, per_call,
                                                 self.redactor).causal:
                matching.append(call)
        return matching

    # mitmproxy hook. Named exactly as mitmproxy expects.
    def request(self, flow) -> None:  # type: ignore[no-untyped-def]
        req = flow.request
        body = req.raw_content or b""
        # The request target: path plus query, as it goes on the wire. mitmproxy's request.path
        # is exactly that, and NOT the absolute URL -- req.url would drag in scheme and host,
        # which are not content out of our context and would manufacture self-matches.
        target = (req.path or "").encode("utf-8", "surrogateescape")
        published = self._active_calls()
        active = published.get("active_calls", [])

        # Match against the UNION of every in-flight call's arguments, then count how many of
        # them individually contain the matched fragment. The union answers "was any of our
        # argument material in this request"; the per-call count is what tells CONTENT_UNIQUE
        # (one candidate of several) from CONTENT_AMBIGUOUS (several) and from
        # CONTENT_MATCH_UNCONTESTED (only one candidate existed). Without the second number the
        # strongest grade would be unearnable and unfalsifiable at once.
        union_digests: frozenset[str] = frozenset()
        for call in active:
            union_digests |= frozenset(call.get("args_digests", []))

        result = _match.match_request(target, body, self.context_index, union_digests,
                                      self.redactor)

        matching = self._calls_whose_own_arguments_matched(active, result, target, body)

        # NUMBER 5'S MATCHER, run beside the k-gram one and never merged into it. The wire is
        # decomposed by the same rule the driver decomposed the arguments with, each token is
        # digested with the run's key, and the comparison is set containment over digests. Not one
        # token of either side's plaintext crosses: the driver published digests, and these are
        # computed here from bytes that were already in this process.
        wire_tokens = _structure.tokens_of_request(
            req.pretty_host, req.path or "", body)
        wire_digests = self.redactor.token_digest_set(wire_tokens)
        call_token_sets = [frozenset(c.get("token_digests", [])) for c in active]
        cand = _match.discriminating_candidates(call_token_sets, wire_digests)

        attributed = _attributed_call(active, matching, cand)

        our_tp_present = _our_traceparent_present(
            attributed.get("traceparent", ""), req.headers.get("traceparent", ""), body)

        occurrence = _match.decide_occurrence(request_observed=True)
        provenance = _match.decide_provenance(
            request_observed=True,
            has_context_match=bool(result.matched_refs),
            has_argument_match=result.causal,
        )

        try:
            dest_ip = flow.server_conn.peername[0] if flow.server_conn.peername else ""
        except Exception:  # noqa: BLE001
            dest_ip = ""

        self._buffer.append(Flow(
            run_id=self.run_id, server_id=published.get("server_id", ""),
            call_id=attributed.get("call_id"), ts=time.time(),
            dest_host=req.pretty_host, dest_ip=dest_ip, scheme=req.scheme, method=req.method,
            body_observed=True, our_traceparent_present=our_tp_present,
            target_bytes=result.target_bytes, target_matched_bytes=result.target_matched_bytes,
            body_bytes=result.body_bytes, body_matched_bytes=result.body_matched_bytes,
            matched_refs=result.matched_refs, causal=result.causal,
            causal_channel=result.causal_channel,
            node_category=classify_host(req.pretty_host), has_time_and_pid=True,
            occurrence=occurrence, provenance=provenance,
            active_calls_in_window=len(active),
            matching_calls_in_window=len(matching),
            structural_match=bool(cand.discriminating),
            structural_contained=len(cand.contained),
            structural_candidates=len(cand.discriminating),
            non_discriminating_calls=cand.non_discriminating_active,
            candidate_token_count=cand.token_count,
            constant_client_path=bool(self.constant_paths
                                      and self.constant_paths.matches(req.pretty_host,
                                                                      req.path or "")),
            # Read from the control file, never inferred from the in-flight set being empty: the
            # launcher phase is what makes a flow impossible to attribute to a call by construction,
            # and an empty list alone cannot say whether the server process even exists yet.
            phase=published.get("phase", ""),
        ))

    def done(self) -> None:
        """Flush buffered flows when mitmdump shuts down, one line at a time, appending.

        Per record, not per buffer, and that is the whole point. The previous version serialised
        the entire buffer in one write_jsonl call and rewrote the file from it, so a single
        unserialisable field raised and destroyed every flow in the run -- which is exactly what
        happened, to a bool field holding b"". One bad record now costs one record and says so on
        stderr, where mitmdump logs it. A capture layer that loses everything on one malformed
        value is worse than one that loses a line, because the empty file reads as "no server
        egressed anything".

        Appending, rather than rewriting, is also what the file needs: mitmdump may restart
        within a run, and re-reading and rewriting the accumulated file is both quadratic and a
        chance to truncate what earlier passes already wrote.
        """
        written = failed = 0
        with self.flows_path.open("a", encoding="utf-8") as fh:
            for row in self._buffer:
                try:
                    fh.write(json.dumps(asdict(row), sort_keys=True,
                                        separators=(",", ":")) + "\n")
                    written += 1
                except (TypeError, ValueError) as exc:
                    failed += 1
                    print(f"[capture_addon] dropped one unserialisable flow: {exc}",
                          file=sys.stderr)
        self._buffer.clear()
        if failed:
            print(f"[capture_addon] wrote {written} flows, dropped {failed}", file=sys.stderr)


addons = [FanoutRecorder()]
