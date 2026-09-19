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

# WHICH PASS PRODUCED A RUN. A run is driven under exactly one of these conditions and the label
# travels with it, because the conditions are not comparable and a figure from one must never be
# read as a figure from the other (docs/PHASES.md, phase B: two passes).
#
#   sequential  one call in flight per server. Numbers 1, 2, 3 and 4 are read from this pass.
#               CONTENT_UNIQUE is unreachable here BY CONSTRUCTION, so the attribution grades of
#               this pass say nothing about whether content matching discriminates.
#   concurrent  waves of N calls in flight per server. The pass that can produce CONTENT_UNIQUE
#               and CONTENT_AMBIGUOUS, and therefore the only one number 5 may be read from.
#   bench       phase A, our own server and our own sink, where ground truth exists.
#   selftest    synthetic fixtures, no capture. Never a measurement of anything.
# WHERE IN A SERVER'S LIFECYCLE A FLOW WAS SEEN. This is not a refinement of attribution, it is a
# precondition of it: a connection that happened before the server process existed cannot have been
# caused by a tool call, whatever a time window says.
#
#   launcher    the package launcher (npx, uvx) is resolving and downloading, and the server process
#               does not exist yet. Egress here is NPM'S or PyPI's, never the server's.
#   handshake   the process exists and has been asked to initialize and list its tools. Egress here
#               is the server's own startup behaviour, and no call has been made.
#   driving     a tool call is in flight.
#   drained     the in-flight set has been cleared: the previous call returned and the next has not
#               been sent, or the corpus is finished. Egress here is the server's, and it is outside
#               every call window.
#
# Why "drained" exists at all, and it is the fix for a measured defect: the sequential driver used to
# leave the last call published after finishing a server, so the NEXT server's launcher traffic was
# attributed to the PREVIOUS server's last call. Four of the ten servers in the first ten-server
# capture showed exactly one package-registry connection each, every one of them pinned to that
# server's final call. That is the same class of error as calling 87 package-registry flows
# DECLARADO, and it is what this field and the clearing that goes with it remove.
PHASE_LAUNCHER = "launcher"
PHASE_HANDSHAKE = "handshake"
PHASE_DRIVING = "driving"
PHASE_DRAINED = "drained"
PHASES_LIFECYCLE = (PHASE_LAUNCHER, PHASE_HANDSHAKE, PHASE_DRIVING, PHASE_DRAINED)

# The phases in which a flow CANNOT have been caused by a tool call of ours, by construction: no
# call had been sent yet. BOTH pre-call phases are here, and the reason is a measurement.
#
# `launcher` was meant to catch the package manager resolving a dependency, and it cannot: the
# process we spawn IS npx or uvx, which resolves the package and then execs the server, so from the
# harness's vantage point the subprocess exists while the MCP server still does not. The first
# ten-server capture with phases recorded put all seven npx servers' package-registry connections in
# `handshake`, not in `launcher`, and every one of them was npm's traffic.
#
# So the line that matters is not "did a process exist" but "had a call been sent". Nothing in either
# phase can have been caused by a call, because there was none. What the two phases still separate is
# WHOSE traffic it is, which is a different question and is answered in disclosure.py against the
# declared package-infrastructure list rather than by guessing from the phase.
PHASES_NOT_CALL_CAUSED = (PHASE_LAUNCHER, PHASE_HANDSHAKE)

PASS_SEQUENTIAL = "sequential"
PASS_CONCURRENT = "concurrent"
PASS_BENCH = "bench"
PASS_SELFTEST = "selftest"
# A control run: a component driven WITHOUT the server under measurement, to find out whether the
# server is a necessary condition for an egress attributed to it. It drives no tool call, so the
# six numbers have no denominator in it and the aggregate refuses to compute them (cli._cmd_aggregate
# and _cmd_figures). Labelled as a pass rather than kept outside the vocabulary because the label is
# what stops a control run being read as a measurement: the run id carries it, the manifest carries
# it, and both commands that could publish from it check it.
PASS_CONTROL = "control"
PASSES = (PASS_SEQUENTIAL, PASS_CONCURRENT, PASS_BENCH, PASS_SELFTEST, PASS_CONTROL)

# The passes that measure a server. A run outside this set may not be read as one: it has no tool
# calls, so every per-call figure would be a ratio over zero dressed as a finding.
PASSES_MEASURING_A_SERVER = (PASS_SEQUENTIAL, PASS_CONCURRENT, PASS_BENCH, PASS_SELFTEST)


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
    # How many calls were driven in the same wave as this one: 1 under the sequential pass, N
    # under the concurrent pass. Recorded per call because "the server errored" and "the server
    # errored at N=10 but not at N=2" are different findings, and a per-flow window count cannot
    # say it: a call that failed may have produced no flow at all. Defaulted so a run written
    # before the two-pass split still reads back.
    wave_size: int = 0


@dataclass
class Flow:
    run_id: str
    server_id: str
    call_id: str | None     # the causing call if attributable, else None
    ts: float               # epoch seconds; evidence for TEMPORAL_ONLY only, never as truth
    dest_host: str
    dest_ip: str
    scheme: str             # "https", "http", or "tcp" for a flow we saw but could not read
    method: str             # HTTP method, or "" for a non-HTTP flow
    body_observed: bool     # did we read the plaintext request (proxy terminated the TLS)?
                            # False means neither channel below was readable, which is what
                            # makes occurrence connection_only and provenance unknown. A GET has
                            # an empty body and a full target: observed-and-empty, not unobserved.
    our_traceparent_present: bool   # did OUR traceparent appear in this outbound request?
    # Two channels, counted apart. The request target is path + query, never the absolute URL.
    # Summing them into one figure would let number 5 be inflated with URLs, so the split is
    # carried all the way to the record rather than reconstructed later. Replaces the former
    # total_bytes/matched_bytes pair, and request_size with it: request_size was already an
    # exact duplicate of total_bytes, and both meant "body length".
    target_bytes: int
    target_matched_bytes: int
    body_bytes: int
    body_matched_bytes: int
    matched_refs: list[str]
    causal: bool
    causal_channel: str     # none / target / body / both -- which channel carried the match
    node_category: str      # local / self_hostable / remote_leaf
    has_time_and_pid: bool  # whether temporal+pid correlation evidence exists for this flow
    # The evidence model's first two claims, recorded as observations (match.decide_occurrence,
    # match.decide_provenance). The THIRD claim, the attribution grade, is deliberately NOT
    # stored: it is derived at aggregation time by match.grade_attribution. Two reasons, and the
    # first is the stronger one. (a) The grade depends on the declared exclusion list in
    # registry/, which is versioned and will change; a grade frozen into the record at capture
    # time could never be recomputed against a newer list, whereas the evidence can, so the same
    # run stays answerable as the list improves. (b) It keeps the capture addon minimal, which
    # matters because it runs inside mitmdump. Cost, stated: reading a flows.jsonl line does not
    # tell the local operator the grade; `aggregate --number 5` does.
    occurrence: str = ""    # observed / connection_only
    provenance: str = ""    # none / context / arguments / both / unknown
    # How many driven calls were in flight when this flow was seen, and in how many of them the
    # matched fragment was present. These two are what make CONTENT_UNIQUE a measurement rather
    # than a restatement of sequential driving: see match.grade_attribution.
    active_calls_in_window: int = 0
    matching_calls_in_window: int = 0
    # THE STRUCTURAL MATCHER'S OWN FIELDS (number 5 only; number 4 keeps the k-gram above).
    #
    # Recorded separately rather than folded into matching_calls_in_window because the two
    # instruments answer different questions and a single pair of counters would make the split
    # unauditable. All four default to 0 so a run captured before F2 reads back unchanged.
    #
    # structural_match        at least one in-flight call survived containment AND discrimination
    # structural_contained    calls whose whole token set was present, BEFORE discrimination
    # structural_candidates   of those, the ones owning a token no neighbour owned
    # non_discriminating_calls  in-flight calls dropped for owning no such token
    # candidate_token_count   tokens of the single surviving candidate, 0 when there is not
    #                         exactly one. One token is never strong evidence, and the grade
    #                         applies that floor.
    #
    # The gap between structural_contained and structural_candidates is threat 18 made visible:
    # a call whose tokens are a subset of a concurrent call's is contained and not a candidate,
    # and without these two numbers side by side that loss is indistinguishable in the output
    # from a flow that never matched anything.
    structural_match: bool = False
    structural_contained: int = 0
    structural_candidates: int = 0
    non_discriminating_calls: int = 0
    candidate_token_count: int = 0
    # Whether this flow's target is one a CLIENT emits with a target that does not vary with the
    # tool call: /robots.txt before every fetch, a browser's own update check
    # (registry/client-constant-paths.json). Recorded AT CAPTURE and not derived later, for the
    # same reason `phase` is: the classification needs the request target, and the target is not
    # stored. Storing the flag instead of the target keeps the record content-free while leaving
    # the denominator of number 5's content figure computable. A run captured before this field
    # existed reads back False, which counts the flow IN, which is the conservative direction.
    constant_client_path: bool = False
    # Which lifecycle phase the driver had published when this flow was seen (PHASES_LIFECYCLE).
    # Defaulted to "" so a run written before the phase existed still reads back, and reported as
    # "unrecorded" rather than guessed: "we did not record the phase" and "the phase was driving"
    # are different claims and only one of them licenses attributing the flow to a call.
    phase: str = ""


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
    # Protocol revision each server ANSWERED with, per registry/probes. Number 3 segments by it,
    # because SEP-414 is a 2026-07-28 change and a server answering an earlier revision predates
    # the convention: not propagating says something about its age, not about uptake. Defaulted
    # so a manifest written before this field existed still reads back.
    server_protocol_versions: dict[str, str] = field(default_factory=dict)
    # Which of PASSES drove this run. Defaulted to "" so a manifest written before the two-pass
    # split still reads back, and reported as "unlabelled" by the aggregate rather than guessed:
    # an unlabelled run is one whose driving condition is unknown, and the grade distribution of a
    # run whose concurrency is unknown means nothing at all.
    pass_name: str = ""
    notes: str = ""
    # Per server, per DECLARED SECRET NAME, whether a value was available when the run was driven.
    # Names and booleans only: this is committed as part of a figure, and a boolean cannot leak a
    # token. It exists because an uncredentialed run is silent by nature (a server missing its
    # token still starts, still handshakes, still produces flows), which is gate rule 10 applied
    # to a credential. Empty dict means no server declared a secret.
    credential_presence: dict = field(default_factory=dict)


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
