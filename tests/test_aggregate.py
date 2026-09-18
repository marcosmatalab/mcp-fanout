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

    # 1: two calls, call A caused 2 flows, call B caused 1 -> mean 1.5.
    assert n[1]["distribution"]["mean"] == 1.5
    assert n[1]["distribution"]["max"] == 2

    # 2: distinct domains per call, same shape here.
    assert n[2]["distribution"]["mean"] == 1.5

    # 3: one of two servers propagated our traceparent.
    assert n[3]["fraction"] == 0.5
    assert n[3]["servers_total"] == 2

    # 4: exactly one flow matched context; matched bytes = 36 (secret) + 19 (DB_PASSWORD line).
    assert n[4]["flows_with_context_match"] == 1
    assert n[4]["matched_bytes"] == 55

    # 5: the decisive number. One EFECTIVO, one DECLARADO, one INDETERMINADO.
    assert n[5]["state_counts"] == {"EFECTIVO": 1, "DECLARADO": 1, "INDETERMINADO": 1}
    assert abs(n[5]["efectivo_fraction"] - 1 / 3) < 1e-4

    # 6: one local node of three distinct nodes.
    assert n[6]["category_counts"]["local"] == 1
    assert n[6]["distinct_nodes"] == 3


def test_aggregate_output_leaks_no_server_names(tmp_path):
    build_demo_run(tmp_path)
    out = str(compute_all(Run.load(tmp_path)))
    # Gate rule 3: aggregate output names no server, host, or tool.
    for forbidden in ("s1", "s2", "api.stripe.com", "api.unknown-vendor.com", "search", "list_files"):
        assert forbidden not in out
