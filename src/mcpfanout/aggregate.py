"""Compute the six numbers from a run. One function per number (doctrine rule 6).

Aggregate output is anonymous by construction (docs/THE-GATE.md rule 3): it emits counts,
ratios and category breakdowns, never a server id, a tool name, or a destination host. The
raw records under runs/ keep those for the local operator; aggregation strips them.

No number depends on a statistical model. Each is a count or a ratio over exact matches. Means
and medians are reported for the per-call distributions (fan-out, domains) because a
distribution is what those questions ask for, not because anything is being estimated.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from . import match as _match
from .classify import Registry, selfhostable_fraction
from .record import Flow, RunManifest, ToolCall, read_jsonl, read_manifest


class Run:
    """A loaded run: manifest, the driven calls, and the observed flows."""

    def __init__(self, manifest: RunManifest, calls: list[ToolCall], flows: list[Flow]) -> None:
        self.manifest = manifest
        self.calls = calls
        self.flows = flows

    @classmethod
    def load(cls, run_dir: str | Path) -> "Run":
        run_dir = Path(run_dir)
        manifest = read_manifest(run_dir / "manifest.json")
        calls = list(read_jsonl(run_dir / "calls.jsonl", ToolCall))
        flows = list(read_jsonl(run_dir / "flows.jsonl", Flow))
        return cls(manifest, calls, flows)


def _flows_by_call(run: Run) -> dict[str, list[Flow]]:
    grouped: dict[str, list[Flow]] = defaultdict(list)
    for f in run.flows:
        # A flow with no attributable call is counted under a sentinel so it is never dropped
        # from fan-out; dropping unattributed egress would flatter the numbers.
        grouped[f.call_id or "<unattributed>"].append(f)
    return grouped


def _dist(values: list[int]) -> dict:
    if not values:
        return {"n": 0, "mean": 0.0, "median": 0.0, "max": 0}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": statistics.median(values),
        "max": max(values),
    }


def number_1(run: Run) -> dict:
    """Outbound connections per tool call. Decides whether the causal union is trivial."""
    per_call = [len(fs) for cid, fs in _flows_by_call(run).items() if cid != "<unattributed>"]
    # Include calls that produced zero egress: a call with no outbound connection is a real,
    # informative data point (the union is trivially empty for it).
    driven = {c.call_id for c in run.calls}
    seen = {f.call_id for f in run.flows if f.call_id}
    per_call += [0] * len(driven - seen)
    return {"number": 1, "name": "outbound_connections_per_tool_call",
            "distribution": _dist(per_call), "command": "make n1"}


def number_2(run: Run) -> dict:
    """Distinct domains per tool call. Sizes the publishable finding."""
    per_call = []
    for cid, fs in _flows_by_call(run).items():
        if cid == "<unattributed>":
            continue
        per_call.append(len({f.dest_host for f in fs}))
    driven = {c.call_id for c in run.calls}
    seen = {f.call_id for f in run.flows if f.call_id}
    per_call += [0] * len(driven - seen)
    return {"number": 2, "name": "distinct_domains_per_tool_call",
            "distribution": _dist(per_call), "command": "make n2"}


def number_3(run: Run) -> dict:
    """Fraction of servers that propagate our traceparent downstream (SEP-414 cooperative path)."""
    servers = {c.server_id for c in run.calls} | {f.server_id for f in run.flows}
    propagating = {f.server_id for f in run.flows if f.our_traceparent_present}
    total = len(servers)
    frac = (len(propagating) / total) if total else 0.0
    return {"number": 3, "name": "servers_propagating_traceparent",
            "fraction": round(frac, 4), "servers_total": total,
            "servers_propagating": len(propagating), "command": "make n3"}


def number_4(run: Run) -> dict:
    """Outbound bytes that literally match context files. Decides whether Half B has signal.

    Reported per channel, always both. The request target (path + query) and the body are both
    bytes leaving for a third party, but they are different evidence: a 40-byte query string and
    a 40kB JSON payload pooled into one "matched bytes" figure describes neither, and a single
    number here is how a reviewer gets told the URL channel was quietly folded in. The totals are
    still given, because withholding them would be its own sleight of hand; they are labelled as
    sums of the two, never as the headline.
    """
    target_hits = [f for f in run.flows if f.target_matched_bytes]
    body_hits = [f for f in run.flows if f.body_matched_bytes]
    any_hits = [f for f in run.flows if f.matched_refs]
    observed = [f for f in run.flows if f.body_observed]
    frac_flows = (len(any_hits) / len(run.flows)) if run.flows else 0.0
    t_matched = sum(f.target_matched_bytes for f in run.flows)
    b_matched = sum(f.body_matched_bytes for f in run.flows)
    t_obs = sum(f.target_bytes for f in observed)
    b_obs = sum(f.body_bytes for f in observed)
    return {"number": 4, "name": "outbound_bytes_matching_context",
            "flows_total": len(run.flows),
            "flows_with_context_match": len(any_hits),
            "flows_with_target_match": len(target_hits),
            "flows_with_body_match": len(body_hits),
            "fraction_flows_with_match": round(frac_flows, 4),
            "target_matched_bytes": t_matched,
            "body_matched_bytes": b_matched,
            "matched_bytes_total": t_matched + b_matched,
            "observed_target_bytes": t_obs,
            "observed_body_bytes": b_obs,
            "observed_outbound_bytes_total": t_obs + b_obs,
            "command": "make n4"}


def number_5(run: Run) -> dict:
    """Fraction of connections causally unifiable by content match. The decisive number.

    Reports the full state distribution, because the doctrine publishes the percentage of each
    state, not a single headline. The headline is the EFECTIVO share.

    And it reports WHICH CHANNEL carried each match, because the headline is only auditable with
    that split. A match in a query string and a match in a request body are both literal causal
    evidence, but they are not the same claim, and an EFECTIVO share that turned out to be all
    target matches would deserve a different reading than one built on bodies. Publishing the
    breakdown next to the fraction is what stops the fraction being taken on trust.
    """
    counts = {_match.EFECTIVO: 0, _match.DECLARADO: 0, _match.INDETERMINADO: 0}
    for f in run.flows:
        counts[f.state] = counts.get(f.state, 0) + 1
    by_channel = {_match.CHANNEL_TARGET: 0, _match.CHANNEL_BODY: 0, _match.CHANNEL_BOTH: 0}
    for f in run.flows:
        if f.state == _match.EFECTIVO and f.causal_channel in by_channel:
            by_channel[f.causal_channel] += 1
    total = len(run.flows)
    efectivo = counts[_match.EFECTIVO]
    return {"number": 5, "name": "connections_causally_unifiable",
            "efectivo_fraction": round((efectivo / total) if total else 0.0, 4),
            "efectivo_by_channel": by_channel,
            "state_counts": counts,
            "flows_total": total,
            "command": "make n5"}


def number_6(run: Run, registry: Registry | None = None) -> dict:
    """Fraction of touched third parties that are themselves self-hostable. Sizes the recursion."""
    hosts = {f.dest_host for f in run.flows if f.dest_host}
    frac, counts = selfhostable_fraction(hosts, registry)
    return {"number": 6, "name": "selfhostable_third_parties",
            "selfhostable_fraction": round(frac, 4),
            "distinct_nodes": sum(counts.values()),
            "category_counts": counts,
            "command": "make n6"}


def compute_all(run: Run, registry: Registry | None = None) -> dict:
    return {
        "run_id": run.manifest.run_id,
        "created": run.manifest.created,
        "salt_fixed": run.manifest.salt_fixed,
        "numbers": [
            number_1(run), number_2(run), number_3(run),
            number_4(run), number_5(run), number_6(run, registry),
        ],
    }
