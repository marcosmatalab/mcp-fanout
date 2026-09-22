"""Compute the six numbers from a run. One function per number (doctrine rule 6).

Aggregate output is anonymous by construction (docs/PROTOCOL.md rule 3): it emits counts,
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
from typing import Any

from . import classify as _classify
from . import match as _match
from . import record as _record
from .classify import ConstantPathList, ExclusionList, Registry, selfhostable_fraction
from .record import Flow, RunManifest, ToolCall, read_jsonl, read_manifest


class Run:
    """A loaded run: manifest, the driven calls, and the observed flows."""

    def __init__(self, manifest: RunManifest, calls: list[ToolCall], flows: list[Flow]) -> None:
        self.manifest = manifest
        self.calls = calls
        self.flows = flows

    @classmethod
    def load(cls, run_dir: str | Path) -> Run:
        run_dir = Path(run_dir)
        manifest = read_manifest(run_dir / "manifest.json")
        calls = list(read_jsonl(run_dir / "calls.jsonl", ToolCall))
        flows = list(read_jsonl(run_dir / "flows.jsonl", Flow))
        return cls(manifest, calls, flows)


def _call_caused_possible(flow: Flow) -> bool:
    """False when the flow was seen before the server process existed, so no call could cause it.

    Unrecorded phases ("" on a run written before the field existed) count as POSSIBLE, because the
    alternative is to silently drop flows from a figure on the strength of a field nobody wrote. The
    aggregate reports the unrecorded share instead, where a reader can see it.
    """
    return flow.phase not in _record.PHASES_NOT_CALL_CAUSED


def _on_package_infrastructure(flow: Flow, exclusions: ExclusionList | None) -> bool:
    """Is this flow's destination on the declared package-infrastructure list?

    Two paths, and the RECORD decides which, not a flag somebody passes in:

    - A captured run carries the hostname, so the declared list is applied to it here, at
      aggregation time. That is what lets a newer list re-answer an old run, which is the same
      argument that keeps the attribution grade out of the record.
    - A REDACTED run (tools/redact_run.py) has no hostname to apply a list to: the hostname is
      what makes a run unpublishable, so it is gone. The answer was computed before it was
      destroyed and carried in `dest_class`, and the manifest records the digest of the list it
      was computed against. Cost, stated: that answer is frozen, and a reader who wants it
      re-derived needs the capture, not the published run. `exclusion_citation` reports the
      carried digest beside the current one so a divergence is visible rather than silent.

    A flow with no class and no list is not on the list, which is the same answer both paths give
    when nothing declares anything.
    """
    if flow.dest_class:
        return flow.dest_class == _record.DEST_PACKAGE_INFRASTRUCTURE
    return exclusions is not None and exclusions.matches(flow.dest_host)


def _classification_is_carried(run: Run) -> bool:
    """True when the run's destinations were classified before its hostnames were redacted."""
    return any(f.dest_class for f in run.flows)


def _carried_classification_note(run: Run, exclusions: ExclusionList | None) -> dict[str, Any]:
    """What a reader needs to check a carried classification, including when it has gone stale."""
    carried = (run.manifest.redaction or {}).get("package_infrastructure_sha256", "")
    out = {
        "classification": "carried by the record: this run is redacted and has no hostnames to "
                          "apply the list to (tools/redact_run.py)",
        "computed_against_sha256": carried or "unrecorded",
    }
    if exclusions is not None and carried:
        out["list_digest_still_matches"] = (carried == exclusions.sha256)
        if carried != exclusions.sha256:
            out["divergence"] = (
                "the committed list has changed since this run was redacted, so the excluded "
                "figure describes the list as it was and not as it is. Re-derive it from the "
                "capture, or re-redact the run")
    return out


def _launcher_flows(run: Run) -> list[Flow]:
    return [f for f in run.flows if not _call_caused_possible(f)]


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


def _dist(values: list[int]) -> dict[str, Any]:
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


def number_1(run: Run, exclusions: ExclusionList | None = None) -> dict[str, Any]:
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
    # The launcher's egress is excluded from every per-call figure BEFORE anything is counted. It is
    # not the server's traffic: `npx -y pkg@ver` resolves and downloads before the server process
    # exists, so a connection seen in that phase cannot be per-call at any rate. It is reported on
    # its own below, never discarded. Measured reason for the exclusion: in the first ten-server
    # capture four servers each showed one package-registry connection pinned to their LAST call,
    # which was the next server's launcher landing in a window nobody had cleared.
    launcher = _launcher_flows(run)
    grouped = {cid: [f for f in fs if _call_caused_possible(f)]
               for cid, fs in _flows_by_call(run).items() if cid != "<unattributed>"}
    grouped = {cid: fs for cid, fs in grouped.items() if fs}
    # Calls that produced zero egress are real, informative data points (the union is trivially
    # empty for them), so they enter every distribution as a zero.
    driven = {c.call_id for c in run.calls}
    seen = {f.call_id for f in run.flows if f.call_id}
    zeros = [0] * len(driven - seen)

    raw = [len(fs) for fs in grouped.values()] + zeros
    hosts = [len({f.dest_host for f in fs}) for fs in grouped.values()] + zeros

    out = {"number": 1, "name": "outbound_connections_per_tool_call",
           "connections_raw": _dist(raw),
           # Counts, apart from every distribution above. A launcher connection is a fact about the
           # package manager, and pooling it with per-call fan-out is how a server gets credited
           # with
           # traffic it never made.
           "launcher_connections": len(launcher),
           "launcher_connections_note": (
               "seen while the launcher was resolving the package, before the server process "
               "existed. Excluded from every per-call figure by construction, never discarded"),
           "flows_with_unrecorded_phase": sum(1 for f in run.flows if not f.phase),
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

    kept = [len([f for f in fs if not _on_package_infrastructure(f, exclusions)])
            for fs in grouped.values()]
    excluded_total = sum(1 for f in run.flows if _on_package_infrastructure(f, exclusions))
    out["connections_excluding_package_infrastructure"] = _dist(kept + zeros)
    out["package_infrastructure_connections"] = excluded_total
    citation: dict[str, Any] = {"loaded": True, **exclusions.citation()}
    if _classification_is_carried(run):
        citation.update(_carried_classification_note(run, exclusions))
    out["exclusion_list"] = citation
    return out


def number_2(run: Run) -> dict[str, Any]:
    """Distinct domains per tool call. Sizes the publishable finding."""
    per_call = []
    for cid, fs in _flows_by_call(run).items():
        if cid == "<unattributed>":
            continue
        # Same exclusion as number 1, for the same reason: the launcher's destination is not a
        # domain the call touched (see number_1's launcher_connections).
        hosts = {f.dest_host for f in fs if _call_caused_possible(f)}
        if hosts:
            per_call.append(len(hosts))
    driven = {c.call_id for c in run.calls}
    seen = {f.call_id for f in run.flows if f.call_id}
    per_call += [0] * len(driven - seen)
    return {"number": 2, "name": "distinct_domains_per_tool_call",
            "distribution": _dist(per_call), "command": "make n2"}


def observability_by_server(run: Run) -> dict[str, Any]:
    """How many servers the capture layer could SEE, which is not the same as how many were driven.

    THE DEFECT THIS FIXES, and it invalidated two published figures. The proxy is selected by
    HTTP(S)_PROXY, so it observes only clients that honour those variables. A server whose client
    does not is driven, answers, egresses, and leaves nothing in flows.jsonl (docs/THREATS.md
    threat 19). Counting it in the denominator of "how many servers propagate a traceparent" turns
    NOT MEASURED into a measured zero, and a measured zero is a claim about the server. It is a
    claim about our instrument.

    Three states, and every one of them is derived from recorded facts rather than inferred:

      proxy_observed        at least one flow reached flows.jsonl for it
      egress_unobserved     no flow, AND it completed at least one driven call, AND the registry
                            says expects_egress. It was asked to do something that leaves the
                            machine, it did not fail, and we saw nothing. That is the blind spot.
      no_egress_expected    no flow and no reason to expect one: the registry says it egresses
                            nothing, or no call of ours succeeded, so silence is the right answer

    COUNTS, NEVER NAMES. Gate rule 3 forbids a server id in published output, so the states are
    published as tallies. The per-server detail lives in the run's own calls.jsonl and flows.jsonl
    for the operator, and `make backstop` shows whether the unobserved ones left the machine at all.
    """
    driven = {c.server_id for c in run.calls} - {""}
    succeeded = {c.server_id for c in run.calls if c.ok} - {""}
    # CALL-CAUSED PHASES ONLY, and that correction matters. The first version of this counted any
    # flow, so a server whose only observed traffic was `npx` fetching its own package came out
    # `proxy_observed` while its API traffic was entirely invisible: the package manager honours
    # the proxy, the server's client does not. Counting the launcher's egress as the server's
    # would hide exactly the blind spot this function exists to expose.
    with_flows = {f.server_id for f in run.flows if _call_caused_possible(f)} - {""}
    declared = set(run.manifest.servers_expecting_egress or ())
    # A run written before the field existed cannot distinguish "egresses nothing by design" from
    # "we could not see it", so it says so instead of picking one. Guessing True would invent a
    # blind spot for every local server; guessing False would hide every real one.
    expectation_recorded = bool(declared)
    states = {}
    for sid in sorted(driven | with_flows):
        if sid in with_flows:
            states[sid] = "proxy_observed"
        elif sid in succeeded and (not expectation_recorded or sid in declared):
            states[sid] = "egress_unobserved"
        else:
            states[sid] = "no_egress_expected"
    tally = {"proxy_observed": 0, "egress_unobserved": 0, "no_egress_expected": 0}
    for state in states.values():
        tally[state] += 1
    out = {"servers_driven_or_seen": len(states), **tally,
           "egress_expectation_recorded": expectation_recorded,
           "what_this_measures": (
               "how many servers the CAPTURE LAYER could see, which is not how many were driven. "
               "A server whose client ignores HTTP(S)_PROXY is driven, answers and egresses while "
               "leaving nothing in flows.jsonl, so counting it as a measured zero would state a "
               "fact about our instrument as a fact about the server (docs/THREATS.md threat 19)"),
           "command": "make n3"}
    if not expectation_recorded:
        out["egress_expectation_note"] = (
            "this run did not record which servers the registry expects to egress, so every "
            "server that completed a call and produced no flow is counted as unobserved. That "
            "over-counts local servers, which egress nothing by design. Re-run to get the "
            "distinction; it is not inferred here")
    if tally["egress_unobserved"]:
        out["warning"] = (
            f"{tally['egress_unobserved']} server(s) completed calls and produced NO observed "
            "flow. Their egress, if any, is invisible to the proxy. Run `make backstop` on this "
            "run's pcap: outbound SYNs to a destination that is not the proxy are the evidence "
            "that traffic left the machine unobserved. No figure below may treat those servers "
            "as having egressed nothing")
    return out


def number_3(run: Run) -> dict[str, Any]:
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

    by_rev: dict[str, dict[str, Any]] = {}
    for sid in sorted(servers):
        rev = revisions.get(sid) or "unknown"
        bucket = by_rev.setdefault(rev, {"servers_total": 0, "servers_propagating": 0})
        bucket["servers_total"] += 1
        if sid in propagating:
            bucket["servers_propagating"] += 1
    for bucket in by_rev.values():
        bucket["fraction"] = round(bucket["servers_propagating"] / bucket["servers_total"], 4)

    total = len(servers)
    # THE DENOMINATOR THAT MAKES THIS A MEASUREMENT. A server whose traffic never reached the
    # proxy did not decline to propagate a traceparent: we never saw it answer the question. Its
    # inclusion turns "not measured" into a measured zero, which is a statement about the server
    # made out of a limit of our instrument. So the headline fraction is over servers with at
    # least one OBSERVED outbound flow, and the all-servers figure is published beside it and
    # explicitly marked not comparable, the same contract number 5 uses for its raw fraction.
    observed = {f.server_id for f in run.flows if _call_caused_possible(f)} - {""}
    obs_propagating = propagating & observed
    return {"number": 3, "name": "servers_propagating_traceparent",
            "by_protocol_revision": by_rev,
            "servers_with_observed_egress": len(observed),
            "servers_propagating_of_observed": len(obs_propagating),
            "fraction_of_observed": (round(len(obs_propagating) / len(observed), 4)
                                     if observed else None),
            "fraction_of_observed_note": (
                "THE FIGURE TO READ. Denominator: servers with at least one flow the proxy "
                "actually saw. A server the proxy never saw is not a server that declined to "
                "propagate; see the observability block and docs/THREATS.md threat 19"),
            "pooled_fraction": round((len(propagating) / total) if total else 0.0, 4),
            "pooled_note": "read the segments; SEP-414 is a 2026-07-28 change, so a server "
                           "answering an earlier revision predates the convention",
            "pooled_fraction_is_not_comparable": (
                "its denominator counts servers whose egress was never observed, so it reports "
                "NOT MEASURED as a zero. Kept because withholding it would hide how much of the "
                "set was invisible, and never to be quoted on its own"),
            "servers_total": total,
            "servers_propagating": len(propagating),
            "observability": observability_by_server(run),
            "command": "make n3"}


def number_4(run: Run) -> dict[str, Any]:
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


def _attributing_match(flow: Flow) -> bool:
    """Which instrument attributes this flow, and it is NOT the one that measures number 4.

    Number 4 asks whether a request carried material from a context file, which is prose, and
    keeps the exact k-gram: `flow.causal` is its signal and nothing here touches it
    (docs/PREREG-F2.md, P6). Number 5 asks whether a request was CAUSED by a specific call, whose
    arguments are structure, and reads the structural matcher.

    A run captured before F2 has `structural_match` False on every flow and would grade every
    content match away. So the k-gram signal is still honoured when the structural fields were
    never written: `structural_contained` is 0 across an entire pre-F2 run and non-zero somewhere
    in any post-F2 run that matched anything. Falling back is the only reading that does not
    silently rewrite an older run's figures into zeros.
    """
    if flow.structural_match:
        return True
    return flow.causal and flow.structural_contained == 0 and flow.structural_candidates == 0


def _attributing_candidates(flow: Flow) -> int:
    if flow.structural_match:
        return flow.structural_candidates
    return flow.matching_calls_in_window


def structural_instrument_state(run: Run) -> dict[str, Any]:
    """Did the structural matcher actually run, or is number 5 quietly reading the old one.

    GATE RULE 10, applied to the instrument this function is part of. `_attributing_match` falls
    back to the k-gram signal when a flow carries no structural fields, which is right for a run
    captured before F2 and is a TRAP for one captured after: if the driver stopped publishing
    `token_digests`, every flow would carry zero structural evidence, every one would fall back,
    and number 5 would report k-gram grades under the structural instrument's name without a
    single test going red. That is the third failure mode in gate rule 10's list, waiting to
    happen a fourth time.

    So the state is DERIVED AND PUBLISHED rather than assumed. A run with calls in flight that
    carried arguments, and not one flow anywhere showing a call's tokens were even considered, is
    reported as `absent`. That is not proof of a defect: a run where no request ever contained any
    argument material looks the same. It is a claim that the instrument left no trace, which is
    the thing a reader must be told before reading a zero as a finding.
    """
    had_calls = any(f.active_calls_in_window > 0 for f in run.flows)
    considered = sum(f.structural_contained for f in run.flows)
    matched = sum(1 for f in run.flows if f.structural_match)
    if not run.flows:
        state = "no_flows"
    elif considered or matched:
        state = "present"
    elif had_calls:
        state = "absent"
    else:
        state = "no_calls_in_flight"
    out = {"state": state,
           "flows_where_a_call_was_contained": considered,
           "flows_attributed_structurally": matched}
    if state == "absent":
        out["warning"] = (
            "calls were in flight and NO flow in this run shows the structural matcher "
            "considering any of them. Either no request carried argument material at all, or the "
            "instrument did not run: a driver that stopped publishing token_digests produces "
            "exactly this, and number 5's grades would then come from the k-gram matcher under "
            "the structural one's name. Check before reading any figure here as a finding "
            "(docs/PROTOCOL.md rule 10)")
    return out


def _content_eligible(flow: Flow) -> bool:
    """Call-caused, and not a target the client emits constantly whatever the call asked for."""
    return _call_caused_possible(flow) and not flow.constant_client_path




def _denominators(run: Run, strong: int, total: int, constant_paths: ConstantPathList | None,
                  exclusions: ExclusionList | None) -> dict[str, Any]:
    """The three fractions, always together, with the raw one marked.

    THIS IS THE THIRD TIME A CONTAMINATED DENOMINATOR HAS BEEN CAUGHT IN THIS PROJECT, which is
    why all three are published rather than the best one. `strong / len(run.flows)` divides by
    every flow in the run, including package-manager traffic that cannot carry an argument and
    flows seen before any call was sent. On the run F2 was pre-registered against, that reads
    0.0551 where the call-caused figure is 0.1842: the same measurement, off by a factor of three,
    and the difference is entirely in what was counted.

    - `strong_attribution_fraction` (raw, over every flow) is NOT COMPARABLE to the others and
      says so in the output. It is kept because discarding it would hide how much of a run is
      machinery.
    - `attributable_fraction` is over flows that could have been caused by a call at all.
    - `content_attributable_fraction` is over those, minus targets a client emits constantly
      whatever the call asked for. This is the only one number 5's pre-registered verdict binds
      to (docs/PREREG-F2.md section 7), and the list that defines it is cited by sha256 so a
      reader can check that it is the one that was frozen before the measurement.
    """
    # Call-caused AND eligible. Both, and the second is not optional: the 82 package-registry
    # flows in the pre-registration run are in the `driving` phase, so a phase filter alone leaves
    # them in and the denominator reads 120 instead of 38. They are excluded by the declared list,
    # exactly as number 1 excludes them, and for the same reason: they cannot carry a tool call's
    # arguments, so counting them measures how noisy a package manager is.
    attributable = [f for f in run.flows
                    if _call_caused_possible(f)
                    and not _on_package_infrastructure(f, exclusions)]
    out: dict[str, Any] = {
        "attributable_denominator": len(attributable),
        "attributable_fraction": (round(strong / len(attributable), 4) if attributable else None),
        "raw_fraction_is_not_comparable": (
            "strong_attribution_fraction divides by every flow in the run, including package "
            "infrastructure and flows seen before any call was sent. It is published so the "
            "share of a run that is machinery stays visible, and it may not be compared with "
            "either figure below or with another run's"),
    }
    if exclusions is None:
        out["attributable_denominator_note"] = (
            "no exclusion list was loaded, so package-infrastructure flows are still IN this "
            "denominator and the fraction is a floor. Never assumed empty: a missing list and an "
            "empty one give the same number and mean opposite things")
    if constant_paths is None:
        out["content_denominator"] = None
        out["content_attributable_fraction"] = None
        out["content_denominator_note"] = (
            "registry/client-constant-paths.json was not loaded, so the content denominator was "
            "NOT computed. It is never assumed empty: an empty list and a missing list would "
            "produce the same number and mean opposite things")
        return out
    content = [f for f in attributable if not f.constant_client_path]
    unflagged = all(not f.constant_client_path for f in run.flows)
    out["content_denominator"] = len(content)
    out["content_attributable_fraction"] = (
        round(strong / len(content), 4) if content else None)
    out["content_denominator_list"] = constant_paths.citation()
    if unflagged:
        out["content_denominator_warning"] = (
            "no flow in this run carries the constant-path flag, so the content denominator "
            "equals the attributable one. Either the run genuinely contained no constant client "
            "chatter, or it was captured before the flag existed. A pre-F2 run reads back False "
            "on every flow, which counts every flow IN, and that is the conservative direction "
            "rather than the flattering one")
    return out


def _discrimination_summary(run: Run) -> dict[str, Any]:
    """How often an agent's own concurrent calls became mutually indistinguishable.

    A FINDING ABOUT THE PHENOMENON, NOT BOOKKEEPING, and that is why it is published rather than
    logged. A call that owns no token distinguishing it from the others in flight cannot be
    attributed by content by ANY implementation of containment (docs/THREATS.md threat 18), and
    the commonest way to produce one is an agent re-reading its own document with more precision.
    Without this figure the loss is invisible: a flow lost that way looks exactly like a flow that
    never matched, so a limit of the method would get read as a weak matcher.

    `contained_but_not_candidate` is the same story per flow: calls whose whole token set was
    present in the request and which the discrimination rule still refused.
    """
    by_window: dict[str, dict[str, Any]] = {}
    for f in run.flows:
        if not _call_caused_possible(f):
            continue
        b = by_window.setdefault(str(f.active_calls_in_window),
                                 {"flows": 0, "non_discriminating_calls": 0,
                                  "contained_but_not_candidate": 0})
        b["flows"] += 1
        b["non_discriminating_calls"] = max(b["non_discriminating_calls"],
                                            f.non_discriminating_calls)
        b["contained_but_not_candidate"] += max(
            0, f.structural_contained - f.structural_candidates)
    return {"discrimination": {
        "by_window_size": by_window,
        "what_this_measures": (
            "per wave size: how many in-flight calls owned no token distinguishing them from "
            "their neighbours, and how many times a call was contained in a request and still "
            "refused as a candidate. Both are threat 18 made visible in the output"),
        "command": "make n5"}}

def number_5(run: Run, exclusions: ExclusionList | None = None,
             constant_paths: ConstantPathList | None = None) -> dict[str, Any]:
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
    passes are two experimental conditions, not two samples of one (docs/PROTOCOL.md). Under the
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
        eligible = not _on_package_infrastructure(f, exclusions)
        grade, reason = _match.grade_attribution(
            traceparent_present=f.our_traceparent_present,
            argument_match=_attributing_match(f),
            active_calls_in_window=f.active_calls_in_window,
            matching_calls_in_window=_attributing_candidates(f),
            eligible=eligible,
            has_time_and_pid=f.has_time_and_pid,
            call_caused_possible=_call_caused_possible(f),
            candidate_token_count=f.candidate_token_count,
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
        eligible = not _on_package_infrastructure(f, exclusions)
        grade, _ = _match.grade_attribution(
            traceparent_present=f.our_traceparent_present,
            argument_match=_attributing_match(f),
            active_calls_in_window=f.active_calls_in_window,
            matching_calls_in_window=_attributing_candidates(f),
            eligible=eligible,
            has_time_and_pid=f.has_time_and_pid,
            call_caused_possible=_call_caused_possible(f),
            candidate_token_count=f.candidate_token_count,
        )
        bucket = by_window.setdefault(str(f.active_calls_in_window), {})
        bucket[grade] = bucket.get(grade, 0) + 1

    total = len(run.flows)
    strong = sum(grades[g] for g in _match.STRONG_ATTRIBUTION)
    max_window = max((f.active_calls_in_window for f in run.flows), default=0)
    pass_name = run.manifest.pass_name or "unlabelled"
    out = {"number": 5, "name": "attribution_grade_distribution",
           "pass": pass_name,
           # THE CAVEAT TRAVELS WITH THE FIGURE, not beside it in a document. The sensor's
           # self-match recall on realistic argument material is below 1 (measured: 0.5 over the
           # negative corpus's four families, docs/CALIBRATION.md "The self-match ceiling"), so
           # half the material it is shown does not match itself even when the call is its own
           # cause and nothing is concurrent. An attributable share measured by such a sensor is at
           # most that fraction of the true share. The value is deliberately NOT copied here: a
           # number duplicated in two places is a number that goes stale in one of them, so this
           # names the command that measures it instead.
           "published_as": "lower_bound",
           "published_as_reason": (
               "the sensor's self-match recall on realistic argument material is below 1, so an "
               "attributable share measured with it is a floor and not an estimate. Measured by "
               "`make inventory`; decomposed per family in docs/CALIBRATION.md, 'The self-match "
               "ceiling', and stated as threat 12 in docs/THREATS.md"),
           "flows_total": total,
           "attribution_grades": grades,
           "attribution_reasons": reasons,
           "content_match_by_channel": by_channel,
           "grades_by_window_size": by_window,
           "strong_attribution_count": strong,
           "strong_attribution_fraction": round((strong / total) if total else 0.0, 4),
           **_denominators(run, strong, total, constant_paths, exclusions),
           **_discrimination_summary(run),
           "structural_instrument": structural_instrument_state(run),
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
            "see docs/PROTOCOL.md, phase B")
    else:
        out["concurrent_driving_note"] = (
            f"flows were seen with up to {max_window} calls in flight, so the grades below are a "
            "measurement rather than a restatement of the driving regime. There is NO ground "
            "truth in this pass: nothing here says a strong attribution was correct. Attribution "
            "precision has a denominator only on the phase A bench, where we caused every "
            "transfer, and it was measured there (docs/PROTOCOL.md, sensor gate). What this pass "
            "measures is how the grades are DISTRIBUTED over real traffic")
    out["exclusion_list"] = ({"loaded": True, **exclusions.citation()} if exclusions
                             else {"loaded": False,
                                   "reason": "no exclusion list, so no flow was graded "
                                             "ineligible; package traffic falls to TEMPORAL_ONLY"})
    return out


def number_6(run: Run, registry: Registry | None = None) -> dict[str, Any]:
    """Fraction of touched third parties that are themselves self-hostable. Sizes the recursion."""
    hosts = {f.dest_host for f in run.flows if f.dest_host}
    if _classification_is_carried(run):
        # A redacted run has label-shaped hostnames, so classifying them by suffix would put every
        # node in the default bucket and report a fraction about the labels. The category was
        # computed per flow at capture time and travels in the record, so it is read back here,
        # per distinct destination, and the output says that it was.
        by_host = {f.dest_host: f.node_category for f in run.flows if f.dest_host}
        counts = {c: 0 for c in (_classify.LOCAL, _classify.SELF_HOSTABLE, _classify.REMOTE_LEAF)}
        for category in by_host.values():
            counts[category] = counts.get(category, 0) + 1
        total = sum(counts.values())
        recursable = counts.get(_classify.LOCAL, 0) + counts.get(_classify.SELF_HOSTABLE, 0)
        frac = (recursable / total) if total else 0.0
    else:
        frac, counts = selfhostable_fraction(hosts, registry)
    obs = observability_by_server(run)
    out = {"number": 6, "name": "selfhostable_third_parties",
           "selfhostable_fraction": round(frac, 4),
           "distinct_nodes": sum(counts.values()),
           "category_counts": counts,
           "observability": obs,
           "command": "make n6"}
    if _classification_is_carried(run):
        out["node_categories"] = (
            "read back from the record. This run is redacted, so its destinations carry a class "
            "label instead of a hostname and nothing can be re-classified from it "
            "(tools/redact_run.py). The categories were computed at capture time, against the "
            "suffix registry as it stood then, and the manifest's redaction block records the "
            "run they came from")
    if obs["egress_unobserved"]:
        # The node set is the set of hosts the PROXY saw. A server the proxy could not see
        # contributes none of its destinations, so this fraction is computed over a truncated
        # population and its denominator is not the population it names.
        out["node_set_is_truncated"] = (
            f"{obs['egress_unobserved']} server(s) completed calls and produced no observed flow, "
            f"so their destinations are absent from these {sum(counts.values())} nodes. This "
            "fraction describes the third parties the capture layer could see, not the third "
            "parties that were touched. See docs/THREATS.md threat 19")
    return out


def driving_summary(run: Run) -> dict[str, Any]:
    """What was driven, and what the servers did with it. NOT one of the six, and needed to
    read them.

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
    by_phase: dict[str, int] = {}
    for f in run.flows:
        by_phase[f.phase or "unrecorded"] = by_phase.get(f.phase or "unrecorded", 0) + 1
    total = len(run.calls)
    errored = sum(1 for c in run.calls if not c.ok)
    return {"name": "driving_summary",
            # Where in each server's lifecycle the observed connections landed. The launcher bucket
            # is the package manager's traffic and is excluded from every per-call figure; the
            # drained bucket is the server's own egress outside any call window.
            "flows_by_lifecycle_phase": by_phase,
            "not_one_of_the_six": ("a denominator, not a finding: the six are ratios over what "
                                   "servers did in response to these calls"),
            "calls_total": total,
            "calls_errored": errored,
            "error_fraction": round((errored / total) if total else 0.0, 4),
            "by_wave_size": by_wave,
            "command": "make numbers"}


def compute_all(run: Run, registry: Registry | None = None,
                exclusions: ExclusionList | None = None,
                constant_paths: ConstantPathList | None = None) -> dict[str, Any]:
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
            number_4(run), number_5(run, exclusions, constant_paths),
            number_6(run, registry),
        ],
    }
