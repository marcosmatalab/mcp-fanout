"""Build a synthetic run without Docker or network, exercising the full compute path.

Purpose: let `mcp-fanout selftest` and the test suite produce a real run directory and real
numbers from the real match/classify/redact code, deterministically, on any machine. This is a
demonstration of the pipeline, NOT a measurement of anything: the flows are hand-built. Output
is written under a directory the caller names and is clearly a selftest, never mixed with a
capture run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import match as _match
from .classify import classify_host
from .record import Flow, RunManifest, ToolCall, write_jsonl, write_manifest
from .redact import DEFAULT_SALT, Redactor

# A synthetic secret long enough to exceed k (16 bytes), so a literal appearance is detectable.
_SECRET = b"AKIA_EXAMPLE_SECRET_TOKEN_0123456789"

# Synthetic session context (the "bait" the agent had in view). Content-free once indexed.
DEMO_CONTEXT: dict[str, bytes] = {
    "context/.env": b"DB_PASSWORD=hunter2\nAWS_ACCESS_KEY_ID=" + _SECRET + b"\nREGION=eu-west-1\n",
    "context/config.py": b"SETTINGS = {\n  'endpoint': 'https://internal.example',\n  'retries': 3,\n}\n",
}


def build_demo_run(out_dir: str | Path, salt: bytes = DEFAULT_SALT) -> Path:
    out_dir = Path(out_dir)
    redactor = Redactor(salt=salt)
    run_id = "selftest"

    # Index the context once (number 4 reference side).
    context_index = _match.build_reference_index(DEMO_CONTEXT, redactor)

    # Two calls: call A carries the secret in its arguments; call B carries no arguments.
    args_a = json.dumps({"query": "load creds", "token": _SECRET.decode()}).encode()
    calls = [
        ToolCall(run_id, "s1", "cA", "search", args_present=True, traceparent="00-aaaa-bbbb-01"),
        ToolCall(run_id, "s2", "cB", "list_files", args_present=False, traceparent="00-cccc-dddd-01"),
    ]
    args_digests = {
        "cA": redactor.kgram_digest_set(args_a),
        "cB": frozenset(),  # argument-less call: nothing can travel, so nothing to match
    }

    # Hand-built outbound bodies, one per intended state.
    body_efectivo = b"POST /ingest {\"payload\":\"" + _SECRET + b"\",\"note\":\"DB_PASSWORD=hunter2\"}"
    body_declarado = b"GET /health?ts=now (no session content here, only a timing correlation)"

    raw_flows = [
        # EFECTIVO: the secret (in call A args) and an .env fragment both appear literally.
        dict(server_id="s1", call_id="cA", dest_host="api.unknown-vendor.com", dest_ip="203.0.113.7",
             scheme="https", method="POST", body=body_efectivo, body_observed=True,
             our_traceparent_present=True, has_time_and_pid=True),
        # DECLARADO: body seen, no content match, but time+pid correlation exists.
        dict(server_id="s1", call_id="cA", dest_host="10.0.0.5", dest_ip="10.0.0.5",
             scheme="http", method="GET", body=body_declarado, body_observed=True,
             our_traceparent_present=False, has_time_and_pid=True),
        # INDETERMINADO: a remote leaf whose body we could not read (TLS not terminated).
        dict(server_id="s2", call_id="cB", dest_host="api.stripe.com", dest_ip="198.51.100.9",
             scheme="tcp", method="", body=b"", body_observed=False,
             our_traceparent_present=False, has_time_and_pid=False),
    ]

    flows: list[Flow] = []
    for i, rf in enumerate(raw_flows):
        body = rf["body"]
        if rf["body_observed"] and body:
            result = _match.match_body(body, context_index, args_digests[rf["call_id"]], redactor)
        else:
            result = _match.MatchResult(total_bytes=len(body), matched_bytes=0, matched_refs=[], causal=False)
        state = _match.decide_state(result.causal, rf["body_observed"], rf["has_time_and_pid"])
        flows.append(Flow(
            run_id=run_id, server_id=rf["server_id"], call_id=rf["call_id"], ts=float(1000 + i),
            dest_host=rf["dest_host"], dest_ip=rf["dest_ip"], scheme=rf["scheme"], method=rf["method"],
            request_size=len(body), body_observed=rf["body_observed"],
            our_traceparent_present=rf["our_traceparent_present"],
            total_bytes=result.total_bytes, matched_bytes=result.matched_bytes,
            matched_refs=result.matched_refs, causal=result.causal, state=state,
            node_category=classify_host(rf["dest_host"]), has_time_and_pid=rf["has_time_and_pid"],
        ))

    corpus_sha = hashlib.sha256(args_a + b"|list_files").hexdigest()
    manifest = RunManifest(
        run_id=run_id, created="1970-01-01T00:00:00Z", salt_fixed=(salt == DEFAULT_SALT),
        k=redactor.k, w=redactor.w, corpus_sha256=corpus_sha,
        server_ids=["s1", "s2"], tool_versions={"harness": "selftest"},
        notes="Synthetic selftest run. Not a measurement.",
    )

    write_manifest(out_dir / "manifest.json", manifest)
    write_jsonl(out_dir / "calls.jsonl", calls)
    write_jsonl(out_dir / "flows.jsonl", flows)
    return out_dir
