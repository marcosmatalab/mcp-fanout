"""On-disk record schemas and JSONL I/O.

A run is three files under runs/<timestamp>/:
  - manifest.json : one RunManifest. What was measured, how, and with which pinned versions.
  - calls.jsonl   : one ToolCall per line. The corpus that was driven into the servers.
  - flows.jsonl   : one Flow per line. Every outbound connection observed, already redacted.

Why JSONL for calls and flows: append-only, one independent record per line, greppable, and
diffable between two runs to prove reproducibility (docs/THE-GATE.md rule 1). Why a separate
JSON manifest: it is read whole, once, and carries the run-level provenance.

Records are content-free by construction. A Flow holds counts, a host, a state and a list of
matched reference ids, never a captured byte. This is the digest-only guarantee at the storage
layer; redact.py enforces it upstream.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Type, TypeVar

T = TypeVar("T")


@dataclass
class ToolCall:
    run_id: str
    server_id: str          # opaque id, never a server name in published output
    call_id: str            # unique within the run; the join key to Flow.call_id
    tool_name: str          # kept for the local operator; scrubbed from aggregate output
    args_present: bool      # whether the call carried arguments that could travel downstream
    traceparent: str        # the W3C traceparent we set in _meta, to test propagation (number 3)
    # Whether the call returned, and if not, why. Defaulted so a run written before these fields
    # existed still reads back. They are here because "2 calls errored" with the reason thrown
    # away is not a measurement: a call that errored after egressing and a call that never
    # reached the network are opposite findings, and only the error text separates them.
    ok: bool = True
    error: str = ""
    # Lines the server wrote to stdout that were not JSON-RPC. MCP stdio reserves stdout for the
    # protocol, so anything else is the server corrupting its own channel -- a property of that
    # server worth recording, not a detail to absorb silently.
    stdout_noise_lines: int = 0


@dataclass
class Flow:
    run_id: str
    server_id: str
    call_id: str | None     # the causing call if attributable, else None
    ts: float               # epoch seconds; used only for DECLARADO correlation, never as truth
    dest_host: str
    dest_ip: str
    scheme: str             # "https", "http", or "tcp" for a flow we saw but could not read
    method: str             # HTTP method, or "" for a non-HTTP flow
    request_size: int
    body_observed: bool     # did we read the plaintext body (proxy terminated the TLS)?
    our_traceparent_present: bool   # did OUR traceparent appear in this outbound request?
    total_bytes: int
    matched_bytes: int
    matched_refs: list[str]
    causal: bool
    state: str              # EFECTIVO / DECLARADO / INDETERMINADO
    node_category: str      # local / self_hostable / remote_leaf
    has_time_and_pid: bool  # whether temporal+pid correlation evidence exists for this flow


@dataclass
class RunManifest:
    run_id: str
    created: str            # ISO 8601 UTC
    salt_fixed: bool        # True when the reproducible default salt was used
    k: int
    w: int
    corpus_sha256: str      # digest of the exact call corpus, so a run pins its own input
    server_ids: list[str] = field(default_factory=list)
    tool_versions: dict[str, str] = field(default_factory=dict)
    notes: str = ""


def write_jsonl(path: str | Path, rows: Iterable) -> None:
    """Write dataclass rows as JSON Lines, one compact object per line, sorted keys.

    Sorted keys and compact separators make two runs diff to an empty diff when nothing changed,
    which is how reproducibility is demonstrated rather than asserted.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            obj = asdict(row) if hasattr(row, "__dataclass_fields__") else row
            fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")


def read_jsonl(path: str | Path, cls: Type[T]) -> Iterator[T]:
    """Read JSON Lines back into dataclass instances of ``cls``."""
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield cls(**json.loads(line))


def write_manifest(path: str | Path, manifest: RunManifest) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(manifest), sort_keys=True, indent=2), encoding="utf-8")


def read_manifest(path: str | Path) -> RunManifest:
    return RunManifest(**json.loads(Path(path).read_text(encoding="utf-8")))
