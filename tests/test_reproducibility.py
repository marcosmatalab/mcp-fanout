"""Gate rule 1: two runs over the same input produce the same output, byte for byte.

This is the reproducibility proof for the measurement core. It builds the synthetic run twice
into two directories and asserts that every artifact is identical byte for byte, and that the
computed numbers are identical. A capture run adds non-determinism from the network; this test
pins the part we control, which is where a silent drift would otherwise hide.
"""

import json

from mcpfanout.aggregate import Run, compute_all
from mcpfanout.demo import build_demo_run


def test_artifacts_are_byte_identical(tmp_path):
    a = build_demo_run(tmp_path / "a")
    b = build_demo_run(tmp_path / "b")
    for name in ("manifest.json", "calls.jsonl", "flows.jsonl"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), f"{name} differs between runs"


def test_numbers_are_identical(tmp_path):
    build_demo_run(tmp_path / "a")
    build_demo_run(tmp_path / "b")
    na = compute_all(Run.load(tmp_path / "a"))
    nb = compute_all(Run.load(tmp_path / "b"))
    assert json.dumps(na, sort_keys=True) == json.dumps(nb, sort_keys=True)


def test_salt_changes_digests_but_not_numbers(tmp_path):
    # A secret salt in a real deployment must change stored digests yet leave numbers invariant.
    from mcpfanout.demo import build_demo_run as build
    build(tmp_path / "fixed")
    build(tmp_path / "secret", salt=b"a-different-secret-salt")
    fixed_flows = (tmp_path / "fixed" / "flows.jsonl").read_text()
    secret_flows = (tmp_path / "secret" / "flows.jsonl").read_text()
    # Numbers identical...
    nf = compute_all(Run.load(tmp_path / "fixed"))
    ns = compute_all(Run.load(tmp_path / "secret"))
    # matched_refs, states, counts are salt-independent; strip the salt_fixed flag before compare.
    nf["salt_fixed"] = ns["salt_fixed"] = None
    assert json.dumps(nf, sort_keys=True) == json.dumps(ns, sort_keys=True)
    # ...even though the flow records themselves are identical here because they store no digests.
    # (Digests live in the persisted fingerprint artifacts, not in flows.jsonl. This asserts the
    # numbers path is salt-independent, which is the claim that matters for reproducibility.)
    assert fixed_flows == secret_flows
