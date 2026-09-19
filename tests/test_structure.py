"""structure.py: one vocabulary, both sides, and the operations the doctrine forbids.

The failure this file mostly guards is silent. If the argument side and the wire side drift into
two slightly different notions of "token", nothing raises: the sets simply stop intersecting and
the matcher reports false negatives that look like servers not forwarding anything.
"""

import json

import pytest

from mcpfanout import structure as S
from mcpfanout.redact import Redactor


# --- One rule, both sides.

@pytest.mark.parametrize("value", [
    "https://example.net/docs/deploy/runbook",
    "https://example.net/search?q=deployment+runbook",
    "docs/deploy/runbook",
    "https://example.net/",
])
def test_the_two_sides_decompose_the_same_string_identically(value):
    """The whole reason this is one module. Asked of the argument side and the wire side."""
    from urllib.parse import urlsplit
    as_argument = S.tokens_of_arguments({"url": value})
    u = urlsplit(value)
    target = (u.path or "/") + (("?" + u.query) if u.query else "")
    as_wire = S.tokens_of_request(u.netloc, target)
    assert as_argument <= as_wire, (sorted(as_argument), sorted(as_wire))


def test_a_call_is_contained_in_its_own_request():
    """The sanity check that stops every figure being zero for the most boring possible reason."""
    args = {"url": "https://example.net/docs/deploy/runbook"}
    wire = S.tokens_of_request("example.net", "/docs/deploy/runbook")
    assert S.contains(S.tokens_of_arguments(args), wire)


def test_the_k_gram_blind_spot_is_gone():
    """The diagnosis that started F2: 20 bytes was invisible at k = 22 and 22 bytes was not."""
    for leaf in ("runbook", "rollback", "checklist"):
        args = {"url": f"https://example.net/docs/deploy/{leaf}"}
        wire = S.tokens_of_request("example.net", f"/docs/deploy/{leaf}")
        assert S.contains(S.tokens_of_arguments(args), wire), leaf


# --- What is deliberately not a token.

def test_non_string_scalars_are_never_evidence():
    """A page size is a knob, not an identity. {"max_length": 2000} must contribute nothing."""
    assert S.tokens_of_arguments({"max_length": 2000, "deep": True, "none": None}) == frozenset()


def test_the_site_root_call_owns_only_its_host():
    """The call that forced the discrimination rule. If this grows a token, the rule loosens."""
    assert S.tokens_of_arguments(
        {"url": "https://example.net/", "max_length": 2000}) == frozenset({"example.net"})


def test_tokens_below_the_floor_are_dropped_after_decoding_not_before():
    """%20 is three bytes and the space it decodes to is one. The floor is about the value."""
    assert "%20" not in S.tokens_of_arguments({"a": "x/%20/yyy"})
    assert S.split_string("ab") == []
    assert S.split_string("abc") == ["abc"]


def test_query_keys_are_not_tokens_but_values_are():
    """A key is the API's vocabulary. `q` would match every request to the same endpoint."""
    toks = S.tokens_of_request("example.net", "/search?query=deployment+runbook")
    assert "deployment runbook" in toks
    assert "query" not in toks


def test_plus_and_percent_encoding_are_both_decoded():
    toks = S.tokens_of_request("example.net", "/search?q=deploy%2Drunbook+notes")
    assert "deploy-runbook notes" in toks


def test_a_query_value_that_is_itself_a_url_is_decomposed_again():
    """The redirector case: ?url=https://host/a/b must expose host, a and b."""
    toks = S.tokens_of_request("proxy.example.net", "/go?url=https%3A%2F%2Finner.example.net%2Fa%2Fbbb")
    assert {"inner.example.net", "bbb"} <= toks


def test_a_json_body_contributes_its_string_leaves():
    body = json.dumps({"locale": "en-US", "text": "the runbook needs an owner", "n": 3})
    toks = S.tokens_of_request("example.net", "/v1/rewrite", body)
    assert "the runbook needs an owner" in toks
    assert "3" not in toks


def test_a_body_that_is_neither_json_nor_a_form_contributes_nothing_by_guesswork():
    toks = S.tokens_of_request("example.net", "/x", b"\x00\x01\x02binary")
    assert toks == frozenset({"example.net"})


# --- The doctrine's boundary, asserted as code.

def test_no_case_folding():
    """Forbidden by docs/DOCTRINE.md: it guesses that two spellings meant one thing."""
    assert not S.contains(S.tokens_of_arguments({"p": "RUNBOOK"}),
                          S.tokens_of_request("example.net", "/docs/runbook"))


def test_no_fuzzy_matching():
    """One byte different is a miss, and a miss is the safe direction."""
    assert not S.contains(S.tokens_of_arguments({"p": "runbok"}),
                          S.tokens_of_request("example.net", "/docs/runbook"))


def test_no_substring_matching_inside_a_segment():
    """Containment is over whole structural tokens, never over byte runs inside them."""
    assert not S.contains(S.tokens_of_arguments({"p": "run"}),
                          S.tokens_of_request("example.net", "/docs/runbook"))


# --- Containment semantics.

def test_a_call_with_no_tokens_is_never_contained():
    """It claims nothing, so it cannot be evidence for anything."""
    assert not S.contains(frozenset(), S.tokens_of_request("example.net", "/anything"))


def test_containment_is_all_tokens_not_any():
    call = S.tokens_of_arguments({"owner": "acme", "repo": "billing"})
    assert not S.contains(call, S.tokens_of_request("api.example.net", "/repos/acme/invoices"))
    assert S.contains(call, S.tokens_of_request("api.example.net", "/repos/acme/billing/x"))


def test_distinguishing_is_empty_when_a_neighbour_owns_everything():
    """Threat 18: the subset call, and the site-root call, both land here."""
    runbook = S.tokens_of_arguments({"url": "https://example.net/docs/deploy/runbook"})
    deeper = S.tokens_of_arguments(
        {"url": "https://example.net/docs/deploy/runbook?section=rollback-steps"})
    assert S.distinguishing(runbook, [deeper]) == frozenset()
    assert S.distinguishing(deeper, [runbook]) == frozenset({"rollback-steps"})


# --- Digests, never tokens.

def test_containment_over_digests_equals_containment_over_tokens():
    """Piece 2 of the proposal, and the thing the whole design rests on."""
    r = Redactor()
    call = S.tokens_of_arguments({"url": "https://example.net/docs/deploy/runbook"})
    for target, expected in (("/docs/deploy/runbook", True),
                             ("/docs/deploy/rollback", False),
                             ("/docs/deploy/runbook?section=x", True),
                             ("/robots.txt", False)):
        wire = S.tokens_of_request("example.net", target)
        assert S.contains(call, wire) is expected
        assert S.contains(r.token_digest_set(call), r.token_digest_set(wire)) is expected


def test_a_token_digest_is_not_a_kgram_digest_of_anything():
    """Domain separation: the two sets are compared against different things."""
    r = Redactor()
    assert r.token_digest("docs") not in r.kgram_digest_set(b"docs" * 20)
