"""The evidence model: three separate claims, and a graded attribution that cannot be gamed.

The single EFECTIVO / DECLARADO / INDETERMINADO column conflated three questions into one word.
The first real capture made the cost concrete: 90 flows graded DECLARADO, of which 87 were a
package registry that cannot carry a tool call's arguments at all. DECLARADO asserts temporal
correlation; the truth there was ineligibility. These tests pin the separation and, above all,
pin the tautology that the strongest grade must not be reachable under sequential driving.
"""

import json
from pathlib import Path

import pytest

from mcpfanout import match as m
from mcpfanout.aggregate import Run, number_4, number_5
from mcpfanout.classify import PACKAGE_INFRASTRUCTURE_PATH, ExclusionList
from mcpfanout.demo import build_demo_run

REPO = Path(__file__).resolve().parent.parent


def _exclusions() -> ExclusionList:
    e = ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH)
    assert e is not None
    return e


def _grade(**kw):
    base = dict(traceparent_present=False, argument_match=False, active_calls_in_window=1,
                matching_calls_in_window=0, eligible=True, has_time_and_pid=True)
    base.update(kw)
    return m.grade_attribution(**base)


# --- The tautology. This is the reason the grade is graded at all.

def test_content_unique_is_unreachable_with_one_call_in_flight():
    """Sequential driving leaves exactly one candidate, so a match discriminates nothing.

    Implementing CONTENT_UNIQUE as "matched, and nothing competed" would make it true of every
    match by construction and would publish 100% strong attribution having told nothing apart.
    """
    grade, reason = _grade(argument_match=True, active_calls_in_window=1,
                           matching_calls_in_window=1)
    assert grade == m.CONTENT_MATCH_UNCONTESTED
    assert grade not in m.STRONG_ATTRIBUTION
    assert "no competing candidate" in reason


def test_content_unique_requires_competition_and_discrimination():
    """Several candidates, fragment in exactly one: that is discrimination, and it is earned."""
    grade, reason = _grade(argument_match=True, active_calls_in_window=4,
                           matching_calls_in_window=1)
    assert grade == m.CONTENT_UNIQUE
    assert grade in m.STRONG_ATTRIBUTION
    assert "1 of 4" in reason


def test_content_ambiguous_when_the_fragment_is_in_several_candidates():
    """Content matched and did not discriminate. A real outcome, and the one bounding precision."""
    grade, reason = _grade(argument_match=True, active_calls_in_window=4,
                           matching_calls_in_window=3)
    assert grade == m.CONTENT_AMBIGUOUS
    assert grade not in m.STRONG_ATTRIBUTION
    assert "did not discriminate" in reason


def test_no_content_unique_is_emitted_by_the_harness_as_it_stands(tmp_path):
    """End to end: with the driver as written, the strongest content grade never appears.

    Asserted over the synthetic run because that is the deterministic one, and the driver
    publishes exactly one in-flight call, so a real run cannot differ on this. If concurrent
    driving lands (phase C) this test is the thing that should be rewritten deliberately, not
    quietly satisfied.
    """
    build_demo_run(tmp_path)
    n5 = number_5(Run.load(tmp_path), _exclusions())
    assert n5["sequential_driving"] is True
    assert n5["max_active_calls_in_window"] == 1
    assert n5["attribution_grades"][m.CONTENT_UNIQUE] == 0
    assert n5["sequential_driving_note"]


def test_strong_attribution_excludes_the_uncontested_grade(tmp_path):
    """The published strong figure must not silently absorb uncontested matches."""
    assert m.CONTENT_MATCH_UNCONTESTED not in m.STRONG_ATTRIBUTION
    assert set(m.STRONG_ATTRIBUTION) == {m.TRACE_PROPAGATED, m.CONTENT_UNIQUE}
    build_demo_run(tmp_path)
    n5 = number_5(Run.load(tmp_path), _exclusions())
    assert n5["strong_attribution_count"] == n5["attribution_grades"][m.TRACE_PROPAGATED]


# --- Package infrastructure is ineligible, not correlated.

def test_package_infrastructure_traffic_is_unattributed_with_a_named_reason():
    """The 87 npm connections are not DECLARADO. They cannot carry arguments at all."""
    grade, reason = _grade(eligible=False, has_time_and_pid=True)
    assert grade == m.UNATTRIBUTED
    assert reason == m.REASON_INELIGIBLE_PACKAGE_INFRASTRUCTURE
    assert "carries no tool-call arguments" in reason


def test_ineligibility_never_suppresses_direct_evidence():
    """The exclusion list withholds a temporal guess; it does not hide a trace or a fragment.

    Same principle as number 1 never filtering its raw count. A package-registry flow that did
    carry our traceparent, or a literal fragment of a call's arguments, would be a finding, and
    a list must not be able to bury it.
    """
    assert _grade(eligible=False, traceparent_present=True)[0] == m.TRACE_PROPAGATED
    assert _grade(eligible=False, argument_match=True, active_calls_in_window=1,
                  matching_calls_in_window=1)[0] == m.CONTENT_MATCH_UNCONTESTED
    assert _grade(eligible=False, argument_match=True, active_calls_in_window=3,
                  matching_calls_in_window=1)[0] == m.CONTENT_UNIQUE


def test_flows_to_package_infrastructure_grade_unattributed_end_to_end(tmp_path):
    """Through the aggregate, with the real published list, not a hand-made one."""
    build_demo_run(tmp_path)
    run = Run.load(tmp_path)
    for f in run.flows:
        f.dest_host = "registry.npmjs.org"
        f.our_traceparent_present = False
        f.causal = False
    n5 = number_5(run, _exclusions())
    assert n5["attribution_grades"][m.UNATTRIBUTED] == len(run.flows)
    assert n5["attribution_grades"][m.TEMPORAL_ONLY] == 0
    assert m.REASON_INELIGIBLE_PACKAGE_INFRASTRUCTURE in n5["attribution_reasons"]


def test_without_an_exclusion_list_nothing_is_called_ineligible(tmp_path):
    """No list means no eligibility claim, and the output says so rather than implying one."""
    build_demo_run(tmp_path)
    run = Run.load(tmp_path)
    for f in run.flows:
        f.dest_host = "registry.npmjs.org"
        f.our_traceparent_present = False
        f.causal = False
    n5 = number_5(run, None)
    assert n5["exclusion_list"]["loaded"] is False
    assert n5["exclusion_list"]["reason"]
    assert n5["attribution_grades"][m.TEMPORAL_ONLY] > 0


# --- The three claims stay apart.

def test_the_three_claims_live_in_separate_numbers(tmp_path):
    """Occurrence and provenance in number 4, attribution in number 5. Never one column."""
    build_demo_run(tmp_path)
    run = Run.load(tmp_path)
    n4, n5 = number_4(run), number_5(run, _exclusions())
    assert "occurrence_counts" in n4 and "provenance_counts" in n4
    assert "attribution_grades" in n5
    # No number may resurrect the conflated column.
    for n in (n4, n5):
        assert "state" not in n and "state_counts" not in n
        assert "EFECTIVO" not in json.dumps(n)


def test_unreadable_requests_have_unknown_provenance_not_none():
    """"We looked and found nothing" and "we could not look" are different findings."""
    assert m.decide_provenance(request_observed=False, has_context_match=False,
                               has_argument_match=False) == m.PROVENANCE_UNKNOWN
    assert m.decide_provenance(request_observed=True, has_context_match=False,
                               has_argument_match=False) == m.PROVENANCE_NONE


def test_provenance_distinguishes_a_file_from_an_argument():
    """A context match is a leak claim; an argument match is a causal key. Not the same claim."""
    assert m.decide_provenance(True, True, False) == m.PROVENANCE_CONTEXT
    assert m.decide_provenance(True, False, True) == m.PROVENANCE_ARGUMENTS
    assert m.decide_provenance(True, True, True) == m.PROVENANCE_BOTH


def test_the_old_state_vocabulary_is_gone_from_the_code():
    """A leftover decide_state would let a caller keep asserting the conflated claim."""
    assert not hasattr(m, "decide_state")
    for name in ("EFECTIVO", "DECLARADO", "INDETERMINADO"):
        assert not hasattr(m, name), f"{name} still exported"
