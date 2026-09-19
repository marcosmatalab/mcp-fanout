"""Compute the six numbers from a run. One function per number (doctrine rule 6).

Aggregate output is anonymous by construction (docs/THE-GATE.md rule 3): it emits counts,
ratios and category breakdowns, never a server id, a tool name, or a destination host. The
raw records under runs/ keep those for the local operator; aggregation strips them.

No number depends on a statistical model. Each is a count or a ratio over exact matches. Means
and medians are reported for the per-call distributions (fan-out, domains) because a
distribution is what those questions ask for, not because anything is being estimated.
"""

from __future__ import annotations

import math
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


def _percentile(sorted_values: list[int], p: float) -> int:
    """Nearest-rank percentile: the smallest observed value at or above rank ceil(p/100 * n).

    Nearest-rank, not linear interpolation, and the difference matters here. Interpolation
    invents a value that was never observed, which for a connection count means reporting
    "2.4 connections". These distributions are small, integer, and heavy-tailed, so an
    interpolated figure would be both fictional and unstable. Every number this returns is a
    value some call actually produced.
    """
    if not sorted_values:
        return 0
    n = len(sorted_values)
    rank = math.ceil((p / 100.0) * n)
    return sorted_values[min(max(rank, 1), n) - 1]


def _dist(values: list[int]) -> dict:
    """A per-call distribution as n, p50, p95 and max. NO MEAN, deliberately.

    The mean is excluded because it misleads on exactly these distributions. The first real
    capture had one call at 89 connections and one at 2: the mean is 45.5, a figure no call
    produced and no architecture decision can be taken from. p50 says what a typical call does,
    p95 and max say how bad the tail gets, and the tail is what decides whether the causal union
    has to survive concurrency. Rejected alternative: report the mean alongside. It would be
    quoted alone, because a single number always is.
    """
    if not values:
        return {"n": 0, "p50": 0, "p95": 0, "max": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "p50": _percentile(ordered, 50),
        "p95": _percentile(ordered, 95),
        "max": ordered[-1],
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
    """Fraction of servers that propagate our traceparent, SEGMENTED by protocol revision.

    Why segmented. SEP-414, which documents trace context in `_meta`, is a minor change of the
    2026-07-28 revision. A server answering 2024-11-05 predates the convention being written
    down, so "it does not propagate" says something about its age, not about the convention's
    uptake. Pooling the two answers the question badly in both directions: it understates uptake
    among servers that could have implemented it, and it implies the older ones declined
    something that did not exist yet. The pooled figure is still published, because withholding
    it would be its own distortion, but it is published next to the segments.

    Servers whose answered revision is unknown get their own bucket rather than being folded in.
    "Not known" is not a revision.
    """
    # Empty server ids are dropped, and that is a correction rather than tidying. A flow seen
    # while no call was in flight carries server_id "" (the control file named nobody), and the
    # set union turned that into an eleventh "server" in a ten-server run: it landed in the
    # "unknown revision" bucket and inflated the denominator of a published fraction with a
    # non-server. Found reading the first ten-server sequential capture, where a package-registry
    # connection arrived between two servers' calls.
    servers = ({c.server_id for c in run.calls} | {f.server_id for f in run.flows}) - {""}
    propagating = {f.server_id for f in run.flows if f.our_traceparent_present} - {""}
    revisions = dict(run.manifest.server_protocol_versions or {})

    by_rev: dict[str, dict] = {}
    for sid in sorted(servers):
        rev = revisions.get(sid) or "unknown"
        bucket = by_rev.setdefault(rev, {"servers_total": 0, "servers_propagating": 0})
        bucket["servers_total"] += 1
        if sid in propagating:
            bucket["servers_propagating"] += 1
    for bucket in by_rev.values():
        bucket["fraction"] = round(bucket["servers_propagating"] / bucket["servers_total"], 4)

    total = len(servers)
    return {"number": 3, "name": "servers_propagating_traceparent",
            "by_protocol_revision": by_rev,
            "pooled_fraction": round((len(propagating) / total) if total else 0.0, 4),
            "pooled_note": "read the segments; SEP-414 is a 2026-07-28 change, so a server "
                           "answering an earlier revision predates the convention",
            "servers_total": total,
            "servers_propagating": len(propagating),
            "command": "make n3"}


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

    WHICH PASS THIS RUN IS, AND WHY THE FIGURE CARRIES IT. Phase B is driven twice, and the two
    passes are two experimental conditions, not two samples of one (docs/PHASES.md). Under the
    sequential pass every window holds one call, so the grade distribution is a restatement of the
    driving regime; under the concurrent pass the same distribution is the measurement. Publishing
    them as one figure would average two conditions, so the pass label is emitted here and the
    per-window breakdown below splits the distribution by how many calls were actually in flight.

    ``grades_by_window_size`` is that breakdown: grade counts keyed by the number of calls in
    flight when the flow was seen. It exists because "strong attribution was 30%" is unreadable
    without knowing at which N, and because the interesting question is how discrimination decays
    as N grows, which a pooled figure cannot show at all. The keys are stringified integers so the
    JSON is stable and sorts predictably.
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

    # The same grading, split by how many calls were in flight. Recomputed rather than tallied
    # inside the loop above only for readability; it is the identical call with the identical
    # inputs, so the two views cannot disagree.
    by_window: dict[str, dict[str, int]] = {}
    for f in run.flows:
        eligible = not (exclusions is not None and exclusions.matches(f.dest_host))
        grade, _ = _match.grade_attribution(
            traceparent_present=f.our_traceparent_present,
            argument_match=f.causal,
            active_calls_in_window=f.active_calls_in_window,
            matching_calls_in_window=f.matching_calls_in_window,
            eligible=eligible,
            has_time_and_pid=f.has_time_and_pid,
        )
        bucket = by_window.setdefault(str(f.active_calls_in_window), {})
        bucket[grade] = bucket.get(grade, 0) + 1

    total = len(run.flows)
    strong = sum(grades[g] for g in _match.STRONG_ATTRIBUTION)
    max_window = max((f.active_calls_in_window for f in run.flows), default=0)
    pass_name = run.manifest.pass_name or "unlabelled"
    out = {"number": 5, "name": "attribution_grade_distribution",
           "pass": pass_name,
           "flows_total": total,
           "attribution_grades": grades,
           "attribution_reasons": reasons,
           "content_match_by_channel": by_channel,
           "grades_by_window_size": by_window,
           "strong_attribution_count": strong,
           "strong_attribution_fraction": round((strong / total) if total else 0.0, 4),
           "strong_attribution_grades": list(_match.STRONG_ATTRIBUTION),
           # None, not False, when there are no flows: with nothing observed, "was this run
           # sequential" is unanswerable from the flows, and False would assert concurrency that
           # was never seen while True would assert a regime the pass did not have. Found on the
           # first concurrent smoke run, against a local control that egressed nothing: the figure
           # said sequential_driving true under a pass driven at N = 10.
           "sequential_driving": (None if total == 0 else max_window <= 1),
           "max_active_calls_in_window": max_window,
           "command": "make n5"}
    if total == 0:
        out["no_flows_note"] = (
            f"no outbound connection was observed at all, so no grade was assigned and nothing "
            f"here describes attribution. Whether this pass drove concurrent calls is a property "
            f"of the run ({pass_name}), not of these flows: see the driving summary for what was "
            f"driven, and note that a server producing zero egress is itself a result")
    elif max_window <= 1:
        out["sequential_driving_note"] = (
            "every flow was seen with at most one call in flight, so CONTENT_UNIQUE is "
            "unreachable by construction and content matches grade as "
            "CONTENT_MATCH_UNCONTESTED. This is the expected outcome of the sequential pass and "
            "is reported as such, never as a finding about content matching. The distribution "
            "that answers whether content matching discriminates comes from the concurrent pass; "
            "see docs/PHASES.md, phase B")
    else:
        out["concurrent_driving_note"] = (
            f"flows were seen with up to {max_window} calls in flight, so the grades below are a "
            "measurement rather than a restatement of the driving regime. There is NO ground "
            "truth in this pass: nothing here says a strong attribution was correct. Attribution "
            "precision has a denominator only on the phase A bench, where we caused every "
            "transfer, and it was measured there (docs/PHASES.md, sensor gate). What this pass "
            "measures is how the grades are DISTRIBUTED over real traffic")
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


def driving_summary(run: Run) -> dict:
    """What was driven, and what the servers did with it. NOT one of the six, and needed to read them.

    Every one of the six is a ratio or a distribution over what the servers did in response to
    calls. A call that errored produced less egress, or none, so a figure read without knowing how
    many calls failed is a figure whose denominator is unstated. Under the concurrent pass this
    goes further: a server that refuses concurrency errors N-1 of a wave's N calls, and its grade
    distribution at that rung then describes one call, not N.

    Broken down by WAVE SIZE, which is the concurrent pass's independent variable, and by nothing
    else: a per-server breakdown would name servers, and gate rule 3 forbids that in published
    output. The per-server detail lives in the run's own waves.jsonl for the operator.
    """
    by_wave: dict[str, dict[str, int]] = {}
    for c in run.calls:
        # "unrecorded" rather than "0": a run driven before wave_size existed did have a wave size,
        # we just did not write it down, and a key of 0 would read as a wave of no calls.
        key = str(c.wave_size) if c.wave_size else "unrecorded"
        bucket = by_wave.setdefault(key, {"calls": 0, "ok": 0, "errored": 0,
                                          "with_arguments": 0, "stdout_noise_lines": 0})
        bucket["calls"] += 1
        bucket["ok" if c.ok else "errored"] += 1
        bucket["with_arguments"] += 1 if c.args_present else 0
        bucket["stdout_noise_lines"] += c.stdout_noise_lines
    total = len(run.calls)
    errored = sum(1 for c in run.calls if not c.ok)
    return {"name": "driving_summary",
            "not_one_of_the_six": ("a denominator, not a finding: the six are ratios over what "
                                   "servers did in response to these calls"),
            "calls_total": total,
            "calls_errored": errored,
            "error_fraction": round((errored / total) if total else 0.0, 4),
            "by_wave_size": by_wave,
            "command": "make numbers"}


def compute_all(run: Run, registry: Registry | None = None,
                exclusions: ExclusionList | None = None) -> dict:
    return {
        "run_id": run.manifest.run_id,
        "created": run.manifest.created,
        "salt_fixed": run.manifest.salt_fixed,
        # Which experimental condition produced these numbers. "unlabelled" for a run written
        # before the two-pass split; never guessed from the flows, because a run that happens to
        # contain no concurrency and a run driven sequentially on purpose are different claims.
        "pass": run.manifest.pass_name or "unlabelled",
        "driving": driving_summary(run),
        "numbers": [
            number_1(run, exclusions), number_2(run), number_3(run),
            number_4(run), number_5(run, exclusions), number_6(run, registry),
        ],
    }
