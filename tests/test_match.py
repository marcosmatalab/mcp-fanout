"""Tests for content matching: the causal union (number 5) and byte coverage (number 4)."""

from mcpfanout import match
from mcpfanout.redact import Redactor

SECRET = b"AKIA_EXAMPLE_SECRET_TOKEN_0123456789"  # 36 bytes, > k


def _r() -> Redactor:
    return Redactor()


def test_causal_union_detects_argument_fragment_in_body():
    r = _r()
    args = b'{"token":"' + SECRET + b'"}'
    body = b"POST /ingest payload=" + SECRET + b" trailing"
    res = match.match_request(b"/ingest", body, {}, r.kgram_digest_set(args), r)
    assert res.causal is True
    assert res.causal_channel == match.CHANNEL_BODY


def test_causal_union_detects_argument_fragment_in_the_query_string():
    """The case the matcher was blind to, and the reason it was renamed.

    A secret in a query string has already left the machine: it is bytes on the wire toward a
    third party. Seeing only the body made numbers 4 and 5 structurally zero for every GET-based
    server, which is the channel most third-party APIs use.
    """
    r = _r()
    args = b'{"token":"' + SECRET + b'"}'
    res = match.match_request(b"/v1/lookup?token=" + SECRET, b"", {},
                              r.kgram_digest_set(args), r)
    assert res.causal is True
    assert res.causal_channel == match.CHANNEL_TARGET
    assert res.body_bytes == 0 and res.body_matched_bytes == 0


def test_causal_channel_reports_both_when_both_carry_it():
    r = _r()
    args = b'{"token":"' + SECRET + b'"}'
    res = match.match_request(b"/v1/lookup?token=" + SECRET, b"payload=" + SECRET, {},
                              r.kgram_digest_set(args), r)
    assert res.causal_channel == match.CHANNEL_BOTH


def test_no_causal_union_when_neither_channel_is_related():
    r = _r()
    args = b'{"token":"' + SECRET + b'"}'
    res = match.match_request(b"/health?ts=now", b"no session content at all here", {},
                              r.kgram_digest_set(args), r)
    assert res.causal is False
    assert res.causal_channel == match.CHANNEL_NONE


def test_the_two_channels_are_counted_separately_never_pooled():
    """Number 5 must not be inflatable with URLs, so the split reaches the result object."""
    r = _r()
    context = {"context/.env": b"AWS_ACCESS_KEY_ID=" + SECRET + b"\n"}
    index = match.build_reference_index(context, r)
    res = match.match_request(b"/v1/lookup?token=" + SECRET,
                              b"prefix............" + SECRET + b"............suffix",
                              index, frozenset(), r)
    # 37, not 36: the context file reads "AWS_ACCESS_KEY_ID=<secret>" and the target reads
    # "?token=<secret>", so the "=" delimiter is shared and the covered run is one byte longer
    # than the secret. Asserted as the exact figure rather than rounded off to the secret's
    # length, because exact k-gram coverage is the claim numbers 4 and 5 rest on.
    assert res.target_matched_bytes == len(SECRET) + 1
    assert res.body_matched_bytes == len(SECRET)  # body has "............" before it, no "="
    # Each coverage is over its OWN channel's length, not a pooled denominator.
    assert 0.0 < res.target_coverage <= 1.0
    assert 0.0 < res.body_coverage < 1.0
    assert res.target_coverage != res.body_coverage


def test_matched_bytes_are_exact_for_a_known_overlap():
    r = _r()
    context = {"context/.env": b"AWS_ACCESS_KEY_ID=" + SECRET + b"\n"}
    index = match.build_reference_index(context, r)
    body = b"prefix............" + SECRET + b"............suffix"
    res = match.match_request(b"/ingest", body, index, frozenset(), r)
    # The full 36-byte secret run is covered; nothing else in the body is in the context.
    assert res.body_matched_bytes == len(SECRET)
    assert res.matched_refs == ["context/.env"]
    assert 0.0 < res.body_coverage < 1.0


def test_empty_request_matches_nothing():
    r = _r()
    res = match.match_request(b"", b"", {"x": r.kgram_digest_set(b"anything at all here")},
                              frozenset(), r)
    assert res.target_matched_bytes == 0 and res.body_matched_bytes == 0
    assert res.target_coverage == 0.0 and res.body_coverage == 0.0
    assert res.causal is False


def test_matched_refs_are_sorted_for_byte_identical_artifacts():
    """Gate rule 1: two runs over the same input must produce the same bytes.

    The refs are a union over two channels now, and set iteration order is not a contract.
    """
    r = _r()
    index = match.build_reference_index(
        {"b.md": b"beta content with enough bytes here", "a.md": b"alpha content with bytes here"}, r)
    res = match.match_request(b"/?x=alpha content with bytes here",
                              b"beta content with enough bytes here", index, frozenset(), r)
    assert res.matched_refs == sorted(res.matched_refs)
    assert res.matched_refs == ["a.md", "b.md"]


def test_the_host_is_not_matched_only_the_request_target():
    """Passing an absolute URL would manufacture self-matches and measure nothing real.

    A context file naming a hostname would "match" every request to that host, which says
    nothing about what leaked. The caller passes path + query; this pins the consequence.
    """
    r = _r()
    context = {"notes.md": b"our vendor is api.unknown-vendor.com and we call it often"}
    index = match.build_reference_index(context, r)
    res = match.match_request(b"/v1/ping", b"", index, frozenset(), r)
    assert res.matched_refs == [], "the host leaked into the matched channel"


# The old single-column decide_state test lived here. It is replaced, not deleted: the three
# claims that took its place are tested in tests/test_evidence_model.py, which also pins the one
# property the old test could not express, that the strongest attribution grade is unreachable
# while the corpus is driven sequentially.
