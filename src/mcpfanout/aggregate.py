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
    # The provenance claim, reported on its own. It says WHAT recognisable material of ours the
    # requests carried, and nothing about which call caused them: that is number 5's claim, and
    # the two are kept in separate numbers so no sentence can join them.
    prov = {k: 0 for k in (_match.PROVENANCE_NONE, _match.PROVENANCE_CONTEXT,
                           _match.PROVENANCE_ARGUMENTS, _match.PROVENANCE_BOTH,
                           _match.PROVENANCE_UNKNOWN)}
    for f in run.flows:
        prov[f.provenance] = prov.get(f.provenance, 0) + 1
    occ = {k: 0 for k in (_match.OCCURRENCE_OBSERVED, _match.OCCURRENCE_CONNECTION_ONLY)}
    for f in run.flows:
        occ[f.occurrence] = occ.get(f.occurrence, 0) + 1
    return {"number": 4, "name": "provenance_coverage",
            "flows_total": len(run.flows),
            # Claim one, occurrence, kept visible here because a provenance figure means nothing
            # without knowing how many requests could be read at all.
            "occurrence_counts": occ,
            # Claim two, provenance.
            "provenance_counts": prov,
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


def number_5(run: Run, exclusions: ExclusionList | None = None) -> dict:
    """Distribution of attribution grades. The decisive number, and the honest shape of it.

    The grade is DERIVED HERE, not read from the record, because it depends on the declared
    exclusion list in registry/, which is versioned and will change. Deriving it at aggregation
    time means the same captured run can be re-graded against a better list; a grade frozen at
    capture time could not. See Flow's comment in record.py.

    What this number does NOT do is publish a single "causally unifiable" fraction. That figure
    was the old EFECTIVO share, and under sequential driving it counted every content match as
    strong evidence when nothing had been discriminated. The grades are published in full, and
    the strong-attribution figure counts only TRACE_PROPAGATED and CONTENT_UNIQUE.

    ``sequential_driving`` is emitted because it is the precondition that makes CONTENT_UNIQUE
    unreachable. While it is true, a reader should expect zero CONTENT_UNIQUE and should not read
    the strong-attribution figure as an answer to whether content matching recovers attribution.
    That question belongs to phase C (docs/PHASES.md).
    """
    grades = {g: 0 for g in _match.ATTRIBUTION_GRADES}
    reasons: dict[str, int] = {}
    by_channel = {_match.CHANNEL_TARGET: 0, _match.CHANNEL_BODY: 0, _match.CHANNEL_BOTH: 0}
    for f in run.flows:
        eligible = not (exclusions is not None and exclusions.matches(f.dest_host))
        grade, reason = _match.grade_attribution(
            traceparent_present=f.our_traceparent_present,
            argument_match=f.causal,
            active_calls_in_window=f.active_calls_in_window,
            matching_calls_in_window=f.matching_calls_in_window,
            eligible=eligible,
            has_time_and_pid=f.has_time_and_pid,
        )
        grades[grade] = grades.get(grade, 0) + 1
        reasons[reason] = reasons.get(reason, 0) + 1
        # Channel split over every flow whose argument material matched, WHATEVER grade it
        # ended at. Not conditioned on the grade: a flow that matched by body and then graded
        # TRACE_PROPAGATED still matched by body, and hiding it would understate the body
        # channel. This split exists so a content figure cannot be quietly inflated with URLs.
        if f.causal and f.causal_channel in by_channel:
            by_channel[f.causal_channel] += 1

    total = len(run.flows)
    strong = sum(grades[g] for g in _match.STRONG_ATTRIBUTION)
    max_window = max((f.active_calls_in_window for f in run.flows), default=0)
    out = {"number": 5, "name": "attribution_grade_distribution",
           "flows_total": total,
           "attribution_grades": grades,
           "attribution_reasons": reasons,
           "content_match_by_channel": by_channel,
           "strong_attribution_count": strong,
           "strong_attribution_fraction": round((strong / total) if total else 0.0, 4),
           "strong_attribution_grades": list(_match.STRONG_ATTRIBUTION),
           "sequential_driving": max_window <= 1,
           "max_active_calls_in_window": max_window,
           "command": "make n5"}
    if max_window <= 1:
        out["sequential_driving_note"] = (
            "every flow was seen with at most one call in flight, so CONTENT_UNIQUE is "
            "unreachable by construction and content matches grade as "
            "CONTENT_MATCH_UNCONTESTED. Whether content matching recovers attribution when time "
            "cannot is answerable only with concurrent calls; see docs/PHASES.md, phase C")
    out["exclusion_list"] = ({"loaded": True, **exclusions.citation()} if exclusions
                             else {"loaded": False,
                                   "reason": "no exclusion list, so no flow was graded "
                                             "ineligible; package traffic falls to TEMPORAL_ONLY"})
    return out


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
            number_4(run), number_5(run, exclusions), number_6(run, registry),
        ],
    }
