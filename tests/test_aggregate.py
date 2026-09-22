"""End-to-end test over the synthetic demo run: locks the six numbers to expected values."""

from pathlib import Path

from mcpfanout.aggregate import Run, compute_all, number_1
from mcpfanout.classify import PACKAGE_INFRASTRUCTURE_PATH, ExclusionList
from mcpfanout.demo import build_demo_run

REPO = Path(__file__).resolve().parent.parent


def _exclusions() -> ExclusionList:
    """The real published list, loaded from the repository, not a stand-in.

    A test fixture list would prove the plumbing and nothing about what the project actually
    excludes. This is the file the aggregate cites.
    """
    e = ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH)
    assert e is not None, f"{PACKAGE_INFRASTRUCTURE_PATH} is missing; number 1 cannot exclude"
    return e


def _numbers(tmp_path, exclusions=None):
    build_demo_run(tmp_path)
    run = Run.load(tmp_path)
    out = compute_all(run, None, exclusions)
    return {n["number"]: n for n in out["numbers"]}


def _numbers_graded(tmp_path):
    """With the real exclusion list, which is what number 5 needs to grade eligibility."""
    return _numbers(tmp_path, _exclusions())


def test_six_numbers_expected_values(tmp_path):
    n = _numbers_graded(tmp_path)

    # 1: two calls; call A caused 3 flows, call B caused 1. No demo flow goes to package
    # infrastructure, so the excluded figure equals the raw one here; the runs where they
    # diverge are real captures, and that divergence is the point of publishing both.
    assert n[1]["connections_raw"] == {"n": 2, "p50": 1, "p95": 3, "max": 3}
    assert n[1]["distinct_hosts"] == {"n": 2, "p50": 1, "p95": 2, "max": 2}
    assert n[1]["connections_excluding_package_infrastructure"] == n[1]["connections_raw"]

    # 2: call A touched 2 distinct hosts, call B touched 1.
    assert n[2]["distribution"] == {"n": 2, "p50": 1, "p95": 2, "max": 2}

    # 3: one of two servers propagated, and the two answered different revisions.
    assert n[3]["pooled_fraction"] == 0.5
    assert n[3]["servers_total"] == 2

    # 4: provenance coverage, with occurrence alongside it because a provenance figure means
    # nothing without knowing how many requests could be read at all. Two flows matched context,
    # one in each channel.
    #
    # These byte counts MOVE WITH k, and they moved: at k = 16 the body figure was 55, the 36-byte
    # secret plus the 19-byte DB_PASSWORD line. At k = 22 (docs/CALIBRATION.md, F1.2) that line is
    # shorter than one k-gram, so it contributes nothing and the figure is the secret alone. That is
    # the false-negative cost of a longer k, priced on a fixture small enough to read: the sweep
    # bought the removal of every structural false positive, and this is what it cost.
    assert n[4]["occurrence_counts"] == {"observed": 3, "connection_only": 1}
    assert n[4]["provenance_counts"]["both"] == 2
    assert n[4]["provenance_counts"]["unknown"] == 1
    assert n[4]["flows_with_context_match"] == 2
    assert n[4]["flows_with_target_match"] == 1
    assert n[4]["flows_with_body_match"] == 1
    assert n[4]["body_matched_bytes"] == 36
    assert n[4]["target_matched_bytes"] == 37
    assert n[4]["matched_bytes_total"] == 73

    # 5: the attribution grade distribution. One flow carried our traceparent (strongest), one
    # matched content with a single call in flight (so uncontested, not unique), one has only
    # time and pid, one was unreadable. Zero CONTENT_UNIQUE, and that is structural while the
    # corpus is driven sequentially; see tests/test_evidence_model.py.
    assert n[5]["attribution_grades"]["TRACE_PROPAGATED"] == 1
    assert n[5]["attribution_grades"]["CONTENT_MATCH_UNCONTESTED"] == 1
    assert n[5]["attribution_grades"]["TEMPORAL_ONLY"] == 1
    assert n[5]["attribution_grades"]["UNATTRIBUTED"] == 1
    assert n[5]["attribution_grades"]["CONTENT_UNIQUE"] == 0
    assert n[5]["sequential_driving"] is True
    assert n[5]["content_match_by_channel"] == {"target": 1, "body": 1, "both": 0}

    # 6: one local node of three distinct nodes.
    assert n[6]["category_counts"]["local"] == 1
    assert n[6]["distinct_nodes"] == 3


def test_aggregate_output_leaks_no_server_names(tmp_path):
    build_demo_run(tmp_path)
    out = str(compute_all(Run.load(tmp_path)))
    # Gate rule 3: aggregate output names no server, host, or tool.
    for forbidden in ("s1", "s2", "api.stripe.com", "api.unknown-vendor.com", "search",
        "list_files"):
        assert forbidden not in out


def test_number_5_never_reports_a_pooled_channel_figure(tmp_path):
    """The channel split has to survive in the published shape, not just in the record.

    A content figure built entirely on query strings reads differently from one built on request
    bodies. If the two are ever summed into a single figure, a reviewer is right to say the
    number was inflated with URLs, so the breakdown is part of the output contract.
    """
    n = _numbers_graded(tmp_path)
    assert set(n[5]["content_match_by_channel"]) == {"target", "body", "both"}
    # And number 4 keeps its two byte counts addressable, with the total clearly labelled a total.
    assert n[4]["target_matched_bytes"] + n[4]["body_matched_bytes"] == n[4]["matched_bytes_total"]
    assert "matched_bytes" not in n[4], "the pooled field is back; it hides the channel split"


# --- Number 1's three figures, and the exclusion list that produces the third.

def test_number_1_publishes_three_figures_together(tmp_path):
    """A raw connection count alone is a true number that answers the wrong question.

    The first real capture measured 87 connections to one package registry during a single call,
    giving a raw mean of 45.5 that says nothing about whether the causal union is hard. The
    three figures have to arrive together or the raw one gets quoted on its own.
    """
    n = _numbers(tmp_path, _exclusions())[1]
    assert "connections_raw" in n
    assert "distinct_hosts" in n
    assert "connections_excluding_package_infrastructure" in n
    # And the old single-figure shape must not come back.
    assert "distribution" not in n, "the single-figure shape is back; raw can be quoted alone"


def test_number_1_raw_is_never_filtered(tmp_path):
    """A server with real fan-out to a listed host must stay visible in the raw figure."""
    build_demo_run(tmp_path)
    run = Run.load(tmp_path)
    # Point every demo flow at a host that IS on the exclusion list.
    for f in run.flows:
        f.dest_host = "registry.npmjs.org"
    n = number_1(run, _exclusions())
    assert n["connections_raw"]["max"] == 3, "the raw figure was filtered"
    assert n["connections_excluding_package_infrastructure"]["max"] == 0
    assert n["package_infrastructure_connections"] == len(run.flows)


def test_number_1_cites_the_exclusion_list_it_used(tmp_path):
    """A declared list, never a silent filter: the output names it, versions it and digests it."""
    n = _numbers(tmp_path, _exclusions())[1]
    cite = n["exclusion_list"]
    assert cite["loaded"] is True
    assert cite["list_name"] == "package-infrastructure"
    assert cite["version"], "an undated exclusion list cannot be checked against the output"
    assert len(cite["sha256"]) == 64
    assert cite["path"] == PACKAGE_INFRASTRUCTURE_PATH
    assert cite["suffix_count"] > 0


def test_number_1_withholds_the_excluded_figure_when_the_list_is_absent(tmp_path):
    """"No list loaded" and "no package traffic" must not produce identical output.

    Computing the excluded figure against an empty list would make them identical, and only one
    of the two is a finding. So the figure is withheld with the reason named.
    """
    n = _numbers(tmp_path, None)[1]
    assert n["connections_excluding_package_infrastructure"] is None
    assert n["package_infrastructure_connections"] is None
    assert n["exclusion_list"]["loaded"] is False
    assert n["exclusion_list"]["reason"]


def test_the_exclusion_list_is_published_in_the_repository():
    """The gate must fail if the list is deleted, or the third figure silently disappears."""
    assert (REPO / PACKAGE_INFRASTRUCTURE_PATH).is_file()
    e = _exclusions()
    # It must carry the hosts the first real capture actually hit, or it excludes nothing useful.
    assert e.matches("registry.npmjs.org")
    assert e.matches("files.pythonhosted.org")
    assert e.matches("pypi.org")
    # And it must NOT swallow general-purpose CDNs, which would hide real egress.
    assert not e.matches("storage.googleapis.com")
    assert not e.matches("example.net")


def test_the_exclusion_citation_names_no_host(tmp_path):
    """Gate rule 3 forbids a hostname in published output, including inside a citation.

    The list is checkable because the file is committed and the digest is published, not because
    the aggregate prints its contents.
    """
    n = _numbers(tmp_path, _exclusions())[1]
    cite = str(n["exclusion_list"])
    for host in _exclusions().suffixes:
        assert host not in cite, f"{host} leaked into the aggregate output"


def test_the_exclusion_citation_never_publishes_an_absolute_path(tmp_path):
    """Loading by absolute path must not leak the operator's directory layout into the output."""
    e = ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH)
    cite = e.citation()
    assert cite["path"] == PACKAGE_INFRASTRUCTURE_PATH
    assert not cite["path"].startswith("/")
    assert "home" not in cite["path"] and "Users" not in cite["path"]


# --- Distribution shape: percentiles, and no mean.

def test_distributions_report_percentiles_and_no_mean(tmp_path):
    """The mean misleads on these distributions, so it is not published at all.

    The first real capture had one call at 89 connections and one at 2. The mean is 45.5, a
    figure no call produced and no architecture decision can rest on. Reporting it alongside the
    percentiles was rejected: a single number always ends up quoted alone.
    """
    n = _numbers_graded(tmp_path)
    for figure in (n[1]["connections_raw"], n[1]["distinct_hosts"],
                   n[1]["connections_excluding_package_infrastructure"], n[2]["distribution"]):
        assert set(figure) == {"n", "p50", "p95", "max"}
        assert "mean" not in figure and "median" not in figure


def test_percentiles_are_nearest_rank_never_interpolated():
    """Every published figure must be a value some call actually produced.

    Linear interpolation would invent "2.4 connections", which is both fictional and unstable on
    small integer distributions.
    """
    from mcpfanout.aggregate import _dist
    d = _dist([89, 2])
    assert d == {"n": 2, "p50": 2, "p95": 89, "max": 89}
    for key in ("p50", "p95", "max"):
        assert isinstance(d[key], int) and d[key] in (2, 89)
    assert _dist([]) == {"n": 0, "p50": 0, "p95": 0, "max": 0}
    assert _dist([7]) == {"n": 1, "p50": 7, "p95": 7, "max": 7}


# --- Number 3 segmented by the revision the server answered.

def test_traceparent_propagation_is_segmented_by_protocol_revision(tmp_path):
    """SEP-414 is a 2026-07-28 change, so an older server predates the convention.

    Pooling the answers understates uptake among servers that could have implemented it and
    implies the older ones declined something that did not exist yet.
    """
    n = _numbers_graded(tmp_path)[3]
    assert set(n["by_protocol_revision"]) == {"2025-11-25", "2024-11-05"}
    assert n["by_protocol_revision"]["2025-11-25"]["servers_propagating"] == 1
    assert n["by_protocol_revision"]["2024-11-05"]["servers_propagating"] == 0
    # The pooled figure is still published, with a pointer to read the segments.
    assert n["pooled_fraction"] == 0.5
    assert n["pooled_note"]


def test_unknown_protocol_revision_gets_its_own_bucket(tmp_path):
    """"Not known" is not a revision, and must not be folded into a real one."""
    build_demo_run(tmp_path)
    run = Run.load(tmp_path)
    run.manifest.server_protocol_versions = {"s1": "2025-11-25"}  # s2 unrecorded
    from mcpfanout.aggregate import number_3
    n = number_3(run)
    assert "unknown" in n["by_protocol_revision"]
    assert n["by_protocol_revision"]["unknown"]["servers_total"] == 1


def test_number_3_does_not_count_a_flow_with_no_server_as_a_server():
    """A connection seen with no call in flight is not an eleventh server.

    Found reading the first ten-server sequential capture: a package-registry connection arrived
    between two servers' calls, so the control file named nobody and the flow carried server_id "".
    The union of call and flow server ids turned that empty string into a server, which landed in
    the "unknown revision" bucket and inflated the denominator of a PUBLISHED fraction. The flow
    itself is still counted everywhere it belongs (fan-out, provenance, grades); what it must not do
    is become a participant.
    """
    from mcpfanout.aggregate import Run, number_3
    from mcpfanout.record import Flow, RunManifest, ToolCall

    def flow(server_id: str) -> Flow:
        return Flow(run_id="r", server_id=server_id, call_id=None, ts=1.0, dest_host="a.example",
                    dest_ip="203.0.113.1", scheme="https", method="GET", body_observed=True,
                    our_traceparent_present=False, target_bytes=1, target_matched_bytes=0,
                    body_bytes=0, body_matched_bytes=0, matched_refs=[], causal=False,
                    causal_channel="none", node_category="remote_leaf", has_time_and_pid=True)

    manifest = RunManifest(run_id="r", created="1970-01-01T00:00:00Z", salt_fixed=True, k=16, w=8,
                           corpus_sha256="0" * 64, server_ids=["s1"],
                           server_protocol_versions={"s1": "2025-11-25"})
    run = Run(manifest, [ToolCall("r", "s1", "c0", "t", True, "tp")], [flow("s1"), flow("")])
    out = number_3(run)
    assert out["servers_total"] == 1, out
    assert "unknown" not in out["by_protocol_revision"], out["by_protocol_revision"]
