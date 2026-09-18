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


def test_six_numbers_expected_values(tmp_path):
    n = _numbers(tmp_path)

    # 1: two calls; call A caused 3 flows, call B caused 1 -> raw mean 2.0. No demo flow goes
    # to package infrastructure, so the excluded figure equals the raw one here; the runs where
    # they diverge are real captures, and the divergence is the point of publishing both.
    assert n[1]["connections_raw"]["mean"] == 2.0
    assert n[1]["connections_raw"]["max"] == 3
    assert n[1]["distinct_hosts"]["mean"] == 1.5

    # 2: call A touched 2 distinct hosts, call B touched 1 -> mean 1.5.
    assert n[2]["distribution"]["mean"] == 1.5
    assert n[2]["distribution"]["max"] == 2

    # 3: one of two servers propagated our traceparent.
    assert n[3]["fraction"] == 0.5
    assert n[3]["servers_total"] == 2

    # 4: two flows matched context, one in each channel, and the channels are reported apart.
    # Body: 36 (secret) + 19 (DB_PASSWORD line) = 55. Target: 37, the secret plus the "="
    # delimiter it shares with AWS_ACCESS_KEY_ID= in the .env reference.
    assert n[4]["flows_with_context_match"] == 2
    assert n[4]["flows_with_target_match"] == 1
    assert n[4]["flows_with_body_match"] == 1
    assert n[4]["body_matched_bytes"] == 55
    assert n[4]["target_matched_bytes"] == 37
    assert n[4]["matched_bytes_total"] == 92

    # 5: the decisive number, with the channel split that keeps it auditable. Two EFECTIVO --
    # one via a request body, one via a query string -- one DECLARADO, one INDETERMINADO.
    # The target one is the case the body-only matcher scored DECLARADO, which is why it is
    # asserted by channel and not just by total.
    assert n[5]["state_counts"] == {"EFECTIVO": 2, "DECLARADO": 1, "INDETERMINADO": 1}
    assert n[5]["efectivo_fraction"] == 0.5
    assert n[5]["efectivo_by_channel"] == {"target": 1, "body": 1, "both": 0}

    # 6: one local node of three distinct nodes.
    assert n[6]["category_counts"]["local"] == 1
    assert n[6]["distinct_nodes"] == 3


def test_aggregate_output_leaks_no_server_names(tmp_path):
    build_demo_run(tmp_path)
    out = str(compute_all(Run.load(tmp_path)))
    # Gate rule 3: aggregate output names no server, host, or tool.
    for forbidden in ("s1", "s2", "api.stripe.com", "api.unknown-vendor.com", "search", "list_files"):
        assert forbidden not in out


def test_number_5_never_reports_a_pooled_channel_figure(tmp_path):
    """The channel split has to survive in the published shape, not just in the record.

    An EFECTIVO share built entirely on query strings reads differently from one built on request
    bodies. If the two are ever summed into a single causal figure, a reviewer is right to say
    number 5 was inflated with URLs, so the breakdown is part of the output contract.
    """
    n = _numbers(tmp_path)
    assert set(n[5]["efectivo_by_channel"]) == {"target", "body", "both"}
    assert sum(n[5]["efectivo_by_channel"].values()) == n[5]["state_counts"]["EFECTIVO"]
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
