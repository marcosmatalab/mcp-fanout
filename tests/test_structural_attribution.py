"""The structural matcher's attribution rules, and the one bug that would undo all of them.

docs/PREREG-F2.md section 4 commits to a test that a flow whose only candidate is an excluded
call comes out UNATTRIBUTED and is never reassigned. That is the file's main job. The reassignment
it guards against is tempting rather than exotic: the addon's older fallback was "if exactly one
call is active, attribute to it", and left in place it hands the flow straight back to the call
the discrimination rule had just rejected, which is the nine false strong attributions of the
no-floor rule returning through a different door.
"""

import pytest

from mcpfanout import match as _match
from mcpfanout import structure as S
from mcpfanout.match import CONTENT_AMBIGUOUS, CONTENT_UNIQUE, UNATTRIBUTED, grade_attribution
from mcpfanout.redact import Redactor

R = Redactor()


def _sets(*arg_dicts):
    return [R.token_digest_set(S.tokens_of_arguments(a)) for a in arg_dicts]


def _wire(host, target, body=b""):
    return R.token_digest_set(S.tokens_of_request(host, target, body))


# The fetch wave at N = 10, reduced to the three calls that matter. Every case below is drawn
# from run 20260919T130847Z-concurrent rather than invented.
RUNBOOK = {"url": "https://example.net/docs/deploy/runbook"}
DEEPER = {"url": "https://example.net/docs/deploy/runbook?section=rollback-steps"}
ROOT = {"url": "https://example.net/", "max_length": 2000}
ROLLBACK = {"url": "https://example.net/docs/deploy/rollback"}


def test_the_root_call_is_contained_in_robots_txt_and_is_still_not_a_candidate():
    """The measured case that justifies the whole discrimination rule."""
    calls = _sets(RUNBOOK, DEEPER, ROOT)
    cand = _match.discriminating_candidates(calls, _wire("example.net", "/robots.txt"))
    assert cand.contained == (2,), "the root call should be contained: its only token is the host"
    assert cand.discriminating == (), "and it must not survive discrimination"
    assert cand.non_discriminating_active == 2


def test_a_flow_whose_only_candidate_was_excluded_is_unattributed_and_not_reassigned():
    """The commitment in docs/PREREG-F2.md section 4, stated as executable.

    There is exactly one active call that contains this request, the rule rejects it, and the
    grade must be UNATTRIBUTED. A fallback to "the only call in the window" would make this
    CONTENT_MATCH_UNCONTESTED or worse, and would be wrong with full confidence.
    """
    calls = _sets(RUNBOOK, DEEPER, ROOT)
    cand = _match.discriminating_candidates(calls, _wire("example.net", "/robots.txt"))
    grade, reason = grade_attribution(
        traceparent_present=False,
        argument_match=bool(cand.discriminating),
        active_calls_in_window=len(calls),
        matching_calls_in_window=len(cand.discriminating),
        eligible=True, has_time_and_pid=True,
        candidate_token_count=cand.token_count)
    assert grade == UNATTRIBUTED, (grade, reason)


def test_the_subset_call_loses_its_own_flow_rather_than_being_guessed():
    """Threat 18, as a test. The runbook call is a subset of the deeper call, so it is excluded,
    and its OWN request has no surviving candidate. The honest outcome is a loss, not a guess."""
    calls = _sets(RUNBOOK, DEEPER, ROOT)
    cand = _match.discriminating_candidates(calls, _wire("example.net", "/docs/deploy/runbook"))
    assert 0 in cand.contained
    assert cand.discriminating == ()
    assert cand.contained != cand.discriminating, "the gap is what threat 18 is measured by"


def test_the_superset_call_still_attributes_cleanly():
    """The cost is paid by the subset call only. The deeper call keeps its own flow."""
    calls = _sets(RUNBOOK, DEEPER, ROOT)
    wire = _wire("example.net", "/docs/deploy/runbook?section=rollback-steps")
    cand = _match.discriminating_candidates(calls, wire)
    assert cand.discriminating == (1,)
    assert cand.token_count == 5


def test_an_unrelated_sibling_attributes_uniquely():
    """Containment has to still work, or the rule above is just a way of matching nothing."""
    calls = _sets(RUNBOOK, DEEPER, ROOT, ROLLBACK)
    cand = _match.discriminating_candidates(calls, _wire("example.net", "/docs/deploy/rollback"))
    assert cand.discriminating == (3,)
    grade, _ = grade_attribution(
        traceparent_present=False, argument_match=True,
        active_calls_in_window=4, matching_calls_in_window=1,
        eligible=True, has_time_and_pid=True, candidate_token_count=cand.token_count)
    assert grade == CONTENT_UNIQUE


# --- The one-token floor, which is a belt over the rule rather than the rule.

def test_a_single_token_candidate_never_earns_the_strongest_grade():
    """{"query": "logs"} is contained in /api/logs?level=warn. One token identifies a class."""
    calls = _sets({"query": "logs"}, {"other": "unrelated-value"})
    cand = _match.discriminating_candidates(calls, _wire("example.net", "/api/logs?level=warn"))
    assert cand.discriminating == (0,) and cand.token_count == 1
    grade, reason = grade_attribution(
        traceparent_present=False, argument_match=True,
        active_calls_in_window=2, matching_calls_in_window=1,
        eligible=True, has_time_and_pid=True, candidate_token_count=cand.token_count)
    assert grade == CONTENT_AMBIGUOUS
    assert "single structural token" in reason


def test_the_floor_does_not_fire_when_the_caller_supplies_no_token_count():
    """Number 4's k-gram path passes 0 and must keep its old behaviour exactly (P6)."""
    grade, _ = grade_attribution(
        traceparent_present=False, argument_match=True,
        active_calls_in_window=3, matching_calls_in_window=1,
        eligible=True, has_time_and_pid=True, candidate_token_count=0)
    assert grade == CONTENT_UNIQUE


# --- Never one token of plaintext.

def test_the_matcher_is_given_digests_and_never_tokens():
    """Piece 2. Every value crossing discriminating_candidates is a 32-char hex digest."""
    calls = _sets(RUNBOOK, DEEPER, ROOT)
    wire = _wire("example.net", "/docs/deploy/runbook")
    for s in [*calls, wire]:
        for value in s:
            assert len(value) == 32 and all(c in "0123456789abcdef" for c in value)
            assert "runbook" not in value and "example" not in value


def test_the_grades_agree_whether_the_sets_are_tokens_or_digests():
    """If they ever diverge, the digest path is a bug, not a design (P2)."""
    plain_calls = [S.tokens_of_arguments(a) for a in (RUNBOOK, DEEPER, ROOT, ROLLBACK)]
    dig_calls = _sets(RUNBOOK, DEEPER, ROOT, ROLLBACK)
    for target in ("/docs/deploy/runbook", "/docs/deploy/rollback", "/robots.txt",
                   "/docs/deploy/runbook?section=rollback-steps", "/"):
        plain = _match.discriminating_candidates(
            plain_calls, S.tokens_of_request("example.net", target))
        dig = _match.discriminating_candidates(dig_calls, _wire("example.net", target))
        assert plain.contained == dig.contained, target
        assert plain.discriminating == dig.discriminating, target
        assert plain.token_count == dig.token_count, target


@pytest.mark.parametrize("n_calls", [1, 2, 5, 10])
def test_a_call_with_no_arguments_is_never_a_candidate(n_calls):
    calls = [frozenset()] * n_calls
    cand = _match.discriminating_candidates(calls, _wire("example.net", "/anything"))
    assert cand.contained == () and cand.discriminating == ()
