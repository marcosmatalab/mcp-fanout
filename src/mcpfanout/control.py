"""The browser control: is a flagged destination the server's, or the browser's it embeds?

WHY THIS EXISTS. Gate rule 7 flagged two destinations on one server, and the obvious reading of
them was "that server embeds a headless browser and the browser checks for updates on its own".
That reading is a diagnosis, and a diagnosis is a guess until something measures it. This module
is the measuring half: it compares the destinations reached by a bare browser, launched with the
same flags through the same proxy with NO MCP server anywhere in the process tree, against the
destinations the server produced. If the flagged hosts appear in both, the cause is located in the
browser by measurement. If they appear only under the server, the diagnosis is wrong and the
finding is about the server after all.

WHAT A MATCH DOES AND DOES NOT ESTABLISH, because the asymmetry is the whole value of the control:

  - Same hosts in both conditions: the server is not a necessary condition for that egress. That
    is causal attribution to the component, in the only form a black-box observer can earn.
  - Hosts only under the server: the browser does not explain them. That is the stronger finding
    and the one that would stop publication.
  - Hosts only in the control: the background set varies between browser launches, which is
    measured here rather than assumed. A single draw of either condition could miss a host that
    both conditions can produce, which is why the control is driven with REPETITIONS and compared
    as a union of draws, with the per-repetition counts kept so a reader can see the variance.

THE RESIDUAL, stated rather than hidden. The control isolates "this browser binary, these launch
flags, this proxy path" from "the MCP server that drives it". It does NOT separate the browser
from the npm driver library the server uses, because the control does not load that library at
all: it spawns the browser binary directly. So a host produced by the library and not by the
browser would show up as "only under the server", which is the safe direction: it would refuse the
diagnosis rather than confirm it wrongly.

OPERATOR-ONLY BY DEFAULT. The output names a server and hostnames, which gate rule 3 forbids in
anything published, so it is written into the run directory. A published form exists only where an
operator has authorised naming the instance, and then it carries the authorisation's own record
with it (see docs/DISCLOSURE-LOG.md).

Standard library only, like the rest of the measurement core.
"""

from __future__ import annotations

from .record import PHASES_NOT_CALL_CAUSED

# The server id the control driver publishes for its navigations. It is not an MCP server and the
# name says so: nothing in registry/servers.yaml carries this id, and a reader of a flows file must
# not be able to mistake a control navigation for a driven tool call.
CONTROL_SERVER_ID = "control-chromium"

VERDICT_REPRODUCED = "cause_reproduced"
VERDICT_PARTIAL = "cause_partially_reproduced"
VERDICT_NOT_REPRODUCED = "cause_not_reproduced"
VERDICT_NOTHING_TO_EXPLAIN = "nothing_under_review"

_VERDICT_MEANING = {
    VERDICT_REPRODUCED: ("every destination under review was also reached by the bare browser, "
                         "so the MCP server is not a necessary condition for any of them"),
    VERDICT_PARTIAL: ("some destinations under review were reached by the bare browser and some "
                      "were not. The ones that were not are NOT explained by the browser and the "
                      "finding about them stands unchanged"),
    VERDICT_NOT_REPRODUCED: ("the bare browser reached none of the destinations under review, so "
                             "the browser diagnosis is refuted and the finding is about the "
                             "server"),
    VERDICT_NOTHING_TO_EXPLAIN: ("no destination of the subject server was under review, so the "
                                 "control has nothing to attribute"),
}


def _hosts_with_counts(flows, *, server_id: str | None = None,
                       call_caused_only: bool = True) -> dict[str, int]:
    """Destination hosts and how many flows reached each, for one server or for all of them.

    ``call_caused_only`` drops the launcher and handshake phases, the same separation
    ``disclosure.check`` makes and for the same reason: a package launcher resolving a dependency
    before the server process exists is not the server's egress, and folding it in here would put
    a package registry in a comparison about a browser.
    """
    out: dict[str, int] = {}
    for f in flows:
        if server_id is not None and (getattr(f, "server_id", "") or "") != server_id:
            continue
        if call_caused_only and getattr(f, "phase", "") in PHASES_NOT_CALL_CAUSED:
            continue
        host = (getattr(f, "dest_host", "") or "").strip().lower()
        if not host:
            continue
        out[host] = out.get(host, 0) + 1
    return dict(sorted(out.items()))


def _match_summary(flows, *, server_id: str | None = None, run_wide: bool = True) -> dict:
    """What our own material did on the wire, reported as TWO channels because they are two.

    They are not the same quantity and conflating them is how a comparison comes to claim more
    than it measured:

      - the CONTEXT channel is measured in bytes (``*_matched_bytes``): how much of a context file
        a request covered. Zero here means no planted bait travelled.
      - the ARGUMENT channel is a BOOLEAN per flow (``causal``): whether any k-gram of the driving
        call's own arguments appeared. It has no byte count by construction, because number 5 asks
        whether a fragment was present, not how much of it was.

    ``causal_flows`` is also the control's own positive control, and that is the reason it is here
    rather than in a note. A control whose background requests carry no match is only evidence if
    the matcher was alive while they were recorded. The control navigates to the corpus URL and
    publishes the corpus call's digests, so the navigation itself SHOULD match: if
    ``causal_flows`` were zero across the whole control run, "nothing matched" would be
    indistinguishable from "nothing could have matched", and the comparison would be worthless in
    exactly the direction that flatters the diagnosis.
    """
    target = body = flows_with_context = causal = total = 0
    for f in flows:
        if server_id is not None and (getattr(f, "server_id", "") or "") != server_id:
            continue
        total += 1
        t = int(getattr(f, "target_matched_bytes", 0) or 0)
        b = int(getattr(f, "body_matched_bytes", 0) or 0)
        target += t
        body += b
        if t or b:
            flows_with_context += 1
        if bool(getattr(f, "causal", False)):
            causal += 1
    argument: dict = {"causal_flows": causal,
                      "means": ("flows carrying a k-gram of the driving call's own arguments")}
    if run_wide:
        # Only over a WHOLE run. Sliced to one host, "no flow carried our material" is the answer
        # being asked for, not a statement about the sensor, and a liveness field in that slice
        # would read as "the matcher was dead for this host", which is not a thing that can happen.
        argument["is_the_sensor_alive"] = causal > 0
        argument["means"] += (". Zero across a whole run means the matcher saw nothing, which is "
                              "not the same as there being nothing to see")
    return {"flows": total,
            "context_channel": {"flows_with_a_match": flows_with_context,
                                "target_matched_bytes": target, "body_matched_bytes": body},
            "argument_channel": argument}


def compare(control_flows, subject_flows, subject_server_id: str,
            under_review: list[str] | tuple[str, ...]) -> dict:
    """Compare a control run's destinations against one server's, for the hosts under review.

    ``under_review`` is the list of hosts gate rule 7 flagged for that server, which comes from
    ``disclosure.check`` rather than from a judgement made here. This module answers "did the bare
    browser reach them too"; it does not decide which hosts deserved reviewing, because that
    decision belongs to the declaration file and to whoever read the server's documentation.

    Returns an operator-only report: it names the server and the hosts.
    """
    control_hosts = _hosts_with_counts(control_flows)
    subject_hosts = _hosts_with_counts(subject_flows, server_id=subject_server_id)

    review = sorted({h.strip().lower() for h in under_review if h.strip()})

    # Per flagged host, whether anything of ours travelled to it, in BOTH conditions. This is the
    # first question a flagged destination raises and the one that decides what the finding is: a
    # background beacon carrying nothing is a note, and the same host carrying a fragment of a tool
    # call's arguments is the phenomenon the six numbers exist to measure. Answering it per host,
    # in the artifact, means the answer has a command behind it instead of being a sentence
    # somebody read off a flows file once.
    carried: dict[str, dict] = {}
    for host in review:
        carried[host] = {
            "under_the_server": _match_summary(
                [f for f in subject_flows
                 if (getattr(f, "server_id", "") or "") == subject_server_id
                 and (getattr(f, "dest_host", "") or "").strip().lower() == host],
                run_wide=False),
            "in_the_control": _match_summary(
                [f for f in control_flows
                 if (getattr(f, "dest_host", "") or "").strip().lower() == host],
                run_wide=False),
        }
    reproduced = [h for h in review if h in control_hosts]
    not_reproduced = [h for h in review if h not in control_hosts]

    if not review:
        verdict = VERDICT_NOTHING_TO_EXPLAIN
    elif not reproduced:
        verdict = VERDICT_NOT_REPRODUCED
    elif not_reproduced:
        verdict = VERDICT_PARTIAL
    else:
        verdict = VERDICT_REPRODUCED

    return {
        "_operator_only": ("names a server and hostnames; gate rule 3 forbids publishing this "
                           "file or quoting a hostname from it without an authorised disclosure"),
        "subject": {
            "server_id": subject_server_id,
            "hosts": subject_hosts,
            "matching": _match_summary(subject_flows, server_id=subject_server_id),
        },
        "control": {
            "server_id": CONTROL_SERVER_ID,
            "hosts": control_hosts,
            "matching": _match_summary(control_flows),
        },
        "under_review": review,
        "did_the_reviewed_hosts_carry_our_material": carried,
        "reproduced_by_the_bare_browser": reproduced,
        "not_reproduced_by_the_bare_browser": not_reproduced,
        "only_in_the_control": sorted(set(control_hosts) - set(subject_hosts)),
        "only_under_the_server": sorted(set(subject_hosts) - set(control_hosts)),
        "verdict": verdict,
        "verdict_means": _VERDICT_MEANING[verdict],
    }


def publishable(report: dict, *, control_run_id: str, subject_run_id: str,
                repetitions: int, dwell_seconds: float, url_source: str,
                authorisation: str) -> dict:
    """The committed form of a comparison, for a finding whose instance an operator authorised.

    Gate rule 3 says aggregate output names nothing, and this file names a server and two hosts.
    That is not the rule being bent: the rule governs what is published WITHOUT authorisation, and
    the gate's own rule 7 describes the other path, where a finding is disclosed and then named.
    So the authorisation travels inside the artifact. Without it there is no publishable form, and
    this function refuses rather than emitting one with an empty field, because an artifact that
    names an instance and cannot say who authorised it is the exact object rule 3 exists to stop.

    What is dropped relative to the operator report: nothing about the hosts, and everything about
    the matching internals, which belong to the run. What is added: how the control was driven, so
    the figure can be read without the run directory it came from.
    """
    if not authorisation.strip():
        raise ValueError("publishable() needs the authorisation record: a named instance may not "
                         "be committed without one (docs/PROTOCOL.md, rule 7)")
    return {
        "normalized": True,
        "names_an_instance": True,
        "authorisation": authorisation,
        "provenance": {
            "control_run_id": control_run_id,
            "subject_run_id": subject_run_id,
            "command": (f"python -m mcpfanout.cli control-compare --run runs/{control_run_id} "
                        f"--against runs/{subject_run_id} --server "
                        f"{report['subject']['server_id']} --publish docs/figures/control"),
            "repetitions": repetitions,
            "dwell_seconds": dwell_seconds,
            "navigation_url_source": url_source,
        },
        "subject": report["subject"],
        "control": report["control"],
        "under_review": report["under_review"],
        "did_the_reviewed_hosts_carry_our_material":
            report["did_the_reviewed_hosts_carry_our_material"],
        "reproduced_by_the_bare_browser": report["reproduced_by_the_bare_browser"],
        "not_reproduced_by_the_bare_browser": report["not_reproduced_by_the_bare_browser"],
        "only_in_the_control": report["only_in_the_control"],
        "only_under_the_server": report["only_under_the_server"],
        "verdict": report["verdict"],
        "verdict_means": report["verdict_means"],
    }
