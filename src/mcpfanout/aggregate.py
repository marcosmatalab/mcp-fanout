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
from . import classify as _classify
from .classify import ExclusionList, Registry, selfhostable_fraction
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


def number_1(run: Run, exclusions: ExclusionList | None = None) -> dict:
    """Outbound connections per tool call, in three figures that are published together.

    One figure here is misleading and the first real capture proved it. mcp-server-fetch opened
    87 connections to registry.npmjs.org while serving one fetch call, because it installs an npm
    package at tool-call time. A raw mean of 45.5 connections per call is a TRUE number that
    answers the WRONG question: those 87 are serial connections to a single host of package
    infrastructure during a known call, so they are trivially attributable. What decides the
    architecture -- whether the causal union is the product or a footnote -- is concurrent
    connections to DISTINCT domains. So three figures, never one:

      connections_raw        every observed connection. Never discarded, never filtered. A
                             server with real fan-out to a host on the exclusion list stays
                             fully visible here.
      distinct_hosts         the same quantity as number 2, repeated here on purpose so the raw
                             figure cannot be quoted without it.
      connections_excluding_package_infrastructure
                             raw minus connections to hosts on the DECLARED list in registry/,
                             cited in the output by name, version and digest.

    If the exclusion list is not loaded, the third figure is None with the reason named, never
    silently computed against an empty list: "no list" and "no package traffic" would otherwise
    produce identical output, and only one of those is a finding.
    """
    grouped = {cid: fs for cid, fs in _flows_by_call(run).items() if cid != "<unattributed>"}
    # Calls that produced zero egress are real, informative data points (the union is trivially
    # empty for them), so they enter every distribution as a zero.
    driven = {c.call_id for c in run.calls}
    seen = {f.call_id for f in run.flows if f.call_id}
    zeros = [0] * len(driven - seen)

    raw = [len(fs) for fs in grouped.values()] + zeros
    hosts = [len({f.dest_host for f in fs}) for fs in grouped.values()] + zeros

    out = {"number": 1, "name": "outbound_connections_per_tool_call",
           "connections_raw": _dist(raw),
           "distinct_hosts": _dist(hosts),
           "distinct_hosts_note": "same quantity as number 2; published here so the raw "
                                  "connection count is never read on its own",
           "command": "make n1"}

    if exclusions is None:
        out["connections_excluding_package_infrastructure"] = None
        out["package_infrastructure_connections"] = None
        out["exclusion_list"] = {
            "loaded": False,
            "reason": f"{_classify.PACKAGE_INFRASTRUCTURE_PATH} not loaded; the excluded figure "
                      f"is withheld rather than computed against an empty list",
        }
        return out

    kept = [len([f for f in fs if not exclusions.matches(f.dest_host)]) for fs in grouped.values()]
    excluded_total = sum(1 for f in run.flows if exclusions.matches(f.dest_host))
    out["connections_excluding_package_infrastructure"] = _dist(kept + zeros)
    out["package_infrastructure_connections"] = excluded_total
    out["exclusion_list"] = {"loaded": True, **exclusions.citation()}
    return out


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


def compute_all(run: Run, registry: Registry | None = None,
                exclusions: ExclusionList | None = None) -> dict:
    return {
        "run_id": run.manifest.run_id,
        "created": run.manifest.created,
        "salt_fixed": run.manifest.salt_fixed,
        "numbers": [
            number_1(run, exclusions), number_2(run), number_3(run),
            number_4(run), number_5(run), number_6(run, registry),
        ],
    }
