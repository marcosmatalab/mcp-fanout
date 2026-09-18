"""End-to-end test over the synthetic demo run: locks the six numbers to expected values."""

from mcpfanout.aggregate import Run, compute_all
from mcpfanout.demo import build_demo_run


def _numbers(tmp_path):
    build_demo_run(tmp_path)
    run = Run.load(tmp_path)
    out = compute_all(run)
    return {n["number"]: n for n in out["numbers"]}


def test_six_numbers_expected_values(tmp_path):
    n = _numbers(tmp_path)

    # 1: two calls; call A caused 3 flows, call B caused 1 -> mean 2.0.
    assert n[1]["distribution"]["mean"] == 2.0
    assert n[1]["distribution"]["max"] == 3

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
