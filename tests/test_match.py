"""Tests for content matching: the causal union (number 5) and byte coverage (number 4)."""

from mcpfanout import match
from mcpfanout.redact import Redactor


def _r() -> Redactor:
    return Redactor()


def test_causal_union_detects_argument_fragment_in_body():
    r = _r()
    secret = b"AKIA_EXAMPLE_SECRET_TOKEN_0123456789"
    args = b'{"token":"' + secret + b'"}'
    body = b"POST /ingest payload=" + secret + b" trailing"
    res = match.match_body(body, {}, r.kgram_digest_set(args), r)
    assert res.causal is True


def test_no_causal_union_when_body_unrelated():
    r = _r()
    args = b'{"token":"AKIA_EXAMPLE_SECRET_TOKEN_0123456789"}'
    body = b"GET /health check with no session content at all here"
    res = match.match_body(body, {}, r.kgram_digest_set(args), r)
    assert res.causal is False


def test_matched_bytes_are_exact_for_a_known_overlap():
    r = _r()
    secret = b"AKIA_EXAMPLE_SECRET_TOKEN_0123456789"  # 36 bytes, > k
    context = {"context/.env": b"AWS_ACCESS_KEY_ID=" + secret + b"\n"}
    index = match.build_reference_index(context, r)
    body = b"prefix............" + secret + b"............suffix"
    res = match.match_body(body, index, frozenset(), r)
    # The full 36-byte secret run is covered; nothing else in the body is in the context.
    assert res.matched_bytes == len(secret)
    assert res.matched_refs == ["context/.env"]
    assert 0.0 < res.coverage < 1.0


def test_empty_body_matches_nothing():
    r = _r()
    res = match.match_body(b"", {"x": r.kgram_digest_set(b"anything at all here")}, frozenset(), r)
    assert res.matched_bytes == 0
    assert res.coverage == 0.0
    assert res.causal is False


def test_decide_state_priority():
    assert match.decide_state(causal=True, body_observed=True, has_time_and_pid=True) == match.EFECTIVO
    assert match.decide_state(causal=False, body_observed=True, has_time_and_pid=True) == match.DECLARADO
    assert match.decide_state(causal=False, body_observed=False, has_time_and_pid=True) == match.INDETERMINADO
    # Content evidence beats correlation even when both are present.
    assert match.decide_state(causal=True, body_observed=False, has_time_and_pid=False) == match.EFECTIVO
