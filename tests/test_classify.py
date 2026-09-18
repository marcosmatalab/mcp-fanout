"""Tests for number 6 classification: self-hostable vs remote leaf."""

from mcpfanout import classify
from mcpfanout.classify import Registry


def test_private_and_loopback_are_local():
    assert classify.classify_host("10.0.0.5") == classify.LOCAL
    assert classify.classify_host("127.0.0.1") == classify.LOCAL
    assert classify.classify_host("localhost") == classify.LOCAL
    assert classify.classify_host("192.168.1.20") == classify.LOCAL


def test_known_saas_is_remote_leaf():
    assert classify.classify_host("api.stripe.com") == classify.REMOTE_LEAF
    assert classify.classify_host("storage.googleapis.com") == classify.REMOTE_LEAF


def test_unknown_public_domain_is_conservatively_remote_leaf():
    # The safe direction: unknown counts against self-hostability.
    assert classify.classify_host("api.some-unknown-vendor.example") == classify.REMOTE_LEAF


def test_registry_can_mark_a_suffix_self_hostable():
    reg = Registry.from_dict({"self_hostable_suffixes": ["internal.corp"]})
    assert classify.classify_host("db.internal.corp", reg) == classify.SELF_HOSTABLE
    # Defaults are extended, never shrunk: stripe is still a leaf.
    assert classify.classify_host("api.stripe.com", reg) == classify.REMOTE_LEAF


def test_fraction_and_breakdown():
    hosts = {"10.0.0.5", "api.stripe.com", "api.unknown.example"}
    frac, counts = classify.selfhostable_fraction(hosts)
    assert counts == {classify.LOCAL: 1, classify.SELF_HOSTABLE: 0, classify.REMOTE_LEAF: 2}
    assert abs(frac - 1 / 3) < 1e-9


def test_empty_host_set_is_zero_not_error():
    frac, counts = classify.selfhostable_fraction(set())
    assert frac == 0.0
    assert sum(counts.values()) == 0
