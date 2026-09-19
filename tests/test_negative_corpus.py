"""The negative-control corpus, and the holdout that keeps its figure honest.

F1.1 asks one question with a number: how often does the matcher affirm a coincidence that does not
exist? The corpus is what produces that number, so the corpus itself has to be checked, and the
checks fall into three groups.

**It really shares no information.** If two calls in a family shared a distinctive value, a match
between them would be a true positive and counting it as a false one would understate the matcher.
Each call declares the values that carry its information, and no declared value of one call may
appear anywhere in another call of the same family.

**It really shares structure.** The opposite failure is a corpus of unrelated strings, which would
be trivially negative and would overstate the matcher. Each family declares the literal byte runs
its calls have in common, and every one of them must appear in every call of that family.

**The holdout is reserved in code, not by memory.** All three F1 pieces are measured against this
one corpus, so tuning until the corpus is happy and then publishing its verdict is the failure mode
to design against. The loader refuses the held-out half to a calibration purpose; these tests fail
if that refusal stops working, if the tuning path reaches for the reserved file by name, or if the
two halves stop being independent.
"""

import json
import re
from pathlib import Path
from urllib.parse import quote, quote_plus, urlparse

import pytest

from mcpfanout.calibrate import (CALIBRATION, HELD_OUT, PURPOSE_CALIBRATION, PURPOSE_PUBLICATION,
                                 HeldOutViolation, claims_match, false_positive_rate,
                                 load_negative, wilson_interval)
from mcpfanout.driver import CallSpec, args_bytes, args_digests_for
from mcpfanout.redact import Redactor

REPO = Path(__file__).resolve().parent.parent
NEGATIVE = REPO / "corpus" / "negative"

# The acceptance criterion F1.1 was given: the published rate rests on at least this many pairs.
MIN_PAIRS = 200


def _raw(half: str) -> dict:
    name = "calibration.json" if half == CALIBRATION else "held-out.json"
    return json.loads((NEGATIVE / name).read_text())


def _corpus(half: str):
    purpose = PURPOSE_CALIBRATION if half == CALIBRATION else PURPOSE_PUBLICATION
    return load_negative(half, purpose=purpose, root=REPO)


def _call_bytes(call) -> bytes:
    """Everything about a call a matcher could possibly see: its arguments and its request."""
    return args_bytes(call.arguments) + b"\x00" + call.target + b"\x00" + call.body


# --- Shape and size.

@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_each_half_has_enough_pairs_to_carry_a_rate(half):
    """The acceptance criterion, read out of the corpus rather than asserted in prose."""
    corpus = _corpus(half)
    assert len(corpus.pairs()) >= MIN_PAIRS, f"{half}: {len(corpus.pairs())} pairs"


@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_every_family_states_what_it_is_for(half):
    for fam in _raw(half)["families"]:
        assert fam["family"] and fam["api"]
        assert len(fam["why"].strip()) > 80, f"{fam['family']}: why is a shrug"
        assert fam["shared_literals"], fam["family"]
        assert fam["calls"], fam["family"]
        for call in fam["calls"]:
            assert call["information"], f"{call['id']}: declares no information"


@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_the_corpus_plants_nothing(half):
    """It is prose and synthetic identifiers. A canary here would be information, not structure."""
    text = (NEGATIVE / ("calibration.json" if half == CALIBRATION else "held-out.json")).read_text()
    assert "CANARY_" not in text
    for real in ("api.github.com", "registry.npmjs.org", "modelcontextprotocol"):
        assert real not in text, f"{real} in a corpus that is supposed to be synthetic"


# --- It shares no information.

@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_no_two_calls_in_a_family_share_information(half):
    """A shared value would make a match a TRUE positive, and counting it would understate the rate."""
    corpus = _corpus(half)
    offenders = []
    for a, b in corpus.pairs():
        blob = _call_bytes(b)
        for item in a.information:
            if item.encode() in blob:
                offenders.append((a.call_id, b.call_id, item))
    assert not offenders, f"shared information: {offenders[:5]}"


def test_the_two_halves_are_independent():
    """A holdout that shares material with the calibration half is not a holdout.

    Checked in both directions and over the whole byte content of each call, not only over ids: the
    point of reserving a half is that nothing tuned against the other half can have seen it.
    """
    cal, held = _corpus(CALIBRATION), _corpus(HELD_OUT)
    assert not ({c.call_id for c in cal.calls} & {c.call_id for c in held.calls})
    for source, other in ((cal, held), (held, cal)):
        other_blob = b"\x00".join(_call_bytes(c) for c in other.calls)
        for call in source.calls:
            for item in call.information:
                assert item.encode() not in other_blob, (
                    f"{call.call_id} information {item!r} also appears in the other half")


# --- It shares structure.

@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_every_declared_shared_literal_is_really_shared(half):
    """Otherwise the corpus is a set of unrelated strings and the rate flatters the matcher."""
    corpus_calls = {c.call_id: c for c in _corpus(half).calls}
    for fam in _raw(half)["families"]:
        for literal in fam["shared_literals"]:
            for call in fam["calls"]:
                blob = _call_bytes(corpus_calls[call["id"]])
                assert literal.encode() in blob, (
                    f"{fam['family']}/{call['id']} does not contain the declared shared literal "
                    f"{literal!r}")


@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_the_arguments_of_a_family_overlap_at_the_shipped_k(half):
    """Structure has to be shared at the granularity the matcher works at, not just visibly.

    This is the mirror of the bench's precondition (tests/test_bench_metrics.py fails if two bench
    fragments share a k-gram). Here at least one pair per family must share one, or the family is
    not exercising the thing it exists to exercise.
    """
    r = Redactor(salt=b"negative-corpus-structure-check")
    corpus = _corpus(half)
    for fam in corpus.families:
        members = [c for c in corpus.calls if c.family == fam]
        sets = [r.kgram_digest_set(args_bytes(c.arguments)) for c in members]
        sharing = any(sets[i] & sets[j] for i in range(len(sets)) for j in range(i + 1, len(sets)))
        assert sharing, f"{fam}: no two calls share a {r.k}-byte run in their arguments"


# --- The request shapes are mechanically consistent with the arguments.

def _expected_target(family: str, args: dict) -> str | None:
    if family == "search_query":
        return "/api/search?q=" + quote_plus(args["query"])
    if family == "rest_path":
        return f"/repos/{args['owner']}/{args['repo']}/contents/{quote(args['path'])}"
    if family == "doc_url":
        return urlparse(args["url"]).path
    if family == "json_post":
        return "/v1/rewrite"
    return None


@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_the_declared_request_is_what_a_client_would_actually_send(half):
    """The requests are data, so they could say anything. Re-derived here from the arguments.

    Without this the corpus could hold a target nobody would ever send, and a false-positive rate
    measured against an invented wire format is a number about our imagination. The derivation is
    the family's own declared rule, so it also pins the corpus to the API shape it claims.
    """
    for fam in _raw(half)["families"]:
        for call in fam["calls"]:
            expected = _expected_target(fam["family"], call["arguments"])
            assert expected is not None, f"no derivation rule for family {fam['family']}"
            assert call["request"]["target"] == expected, call["id"]
            if fam["family"] == "json_post":
                body = json.loads(call["request"]["body"])
                assert body["text"] == call["arguments"]["text"]
                assert body["locale"] == call["arguments"]["locale"]
            else:
                assert call["request"]["body"] == ""


# --- The matcher is asked the same question the addon asks.

def test_the_measurement_uses_the_drivers_own_argument_serialisation():
    """A second way of serialising arguments would make this figure describe a matcher nobody ships."""
    call = _corpus(CALIBRATION).calls[0]
    r = Redactor()
    assert sorted(r.kgram_digest_set(args_bytes(call.arguments))) == \
        args_digests_for(CallSpec("t", call.arguments), r)


def test_a_call_matches_its_own_request_so_the_measurement_can_detect_anything():
    """The sanity check that stops a rate of zero meaning "the matcher is switched off".

    A call's own arguments must be found in its own request wherever the value travels literally. If
    this failed, every false-positive figure would be zero for the most boring possible reason.
    """
    r = Redactor()
    corpus = _corpus(CALIBRATION)
    for family in ("doc_url", "json_post"):
        call = next(c for c in corpus.calls if c.family == family)
        assert claims_match(call, call, r), f"{family}: the matcher cannot even find itself"


# --- The holdout guard.

def test_the_holdout_is_refused_to_a_calibration_purpose():
    with pytest.raises(HeldOutViolation):
        load_negative(HELD_OUT, purpose=PURPOSE_CALIBRATION, root=REPO)


def test_the_calibration_half_is_available_for_both_purposes():
    """Nothing is gained by restricting the tuning half; the asymmetry is the whole design."""
    assert load_negative(CALIBRATION, purpose=PURPOSE_CALIBRATION, root=REPO).calls
    assert load_negative(CALIBRATION, purpose=PURPOSE_PUBLICATION, root=REPO).calls


def test_only_the_loader_names_the_reserved_file():
    """A tuning path that opens the reserved file by name would walk around the guard.

    So the filename exists in exactly one place in src/: the loader's own table. Anything that wants
    it has to come through load_negative and declare a purpose.
    """
    offenders = []
    for path in sorted((REPO / "src").rglob("*.py")):
        if "held-out.json" in path.read_text() and path.name != "calibrate.py":
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"the reserved file is named outside the loader: {offenders}"


def test_the_harness_and_docs_do_not_quietly_measure_the_holdout():
    """The published figure is produced by one command; nothing else may reach for that half.

    harness/ drives captures and must never touch the calibration corpus at all, in either half:
    a capture that read it would be mixing a fixture into a measurement.
    """
    for path in sorted((REPO / "harness").rglob("*")):
        if path.is_file() and path.suffix in (".py", ".sh"):
            text = path.read_text()
            assert "corpus/negative" not in text, f"{path.name} reaches into the negative corpus"


# --- The interval.

def test_wilson_at_zero_successes_is_not_a_claim_of_certainty():
    """The reason Wilson is used at all: zero observed is not zero probability."""
    lo, hi = wilson_interval(0, 224)
    assert lo == 0.0
    assert 0.0 < hi < 0.05, hi


def test_wilson_narrows_as_the_sample_grows():
    narrow = wilson_interval(10, 1000)
    wide = wilson_interval(1, 100)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_wilson_brackets_the_observed_rate():
    for successes, n in ((0, 10), (1, 10), (5, 10), (10, 10), (62, 224)):
        lo, hi = wilson_interval(successes, n)
        assert lo <= successes / n <= hi, (successes, n, lo, hi)


def test_an_empty_sample_reports_total_ignorance_rather_than_zero():
    assert wilson_interval(0, 0) == (0.0, 1.0)


# --- The figure itself.

def test_the_figure_reports_per_family_and_not_only_pooled():
    """The families are deliberately unequal, so a pooled rate alone hides which shapes are unsafe."""
    out = false_positive_rate(_corpus(CALIBRATION), Redactor())
    assert set(out["by_family"]) == set(_corpus(CALIBRATION).families)
    assert out["pairs"] == sum(f["pairs"] for f in out["by_family"].values())
    assert out["false_positives"] == sum(f["false_positives"] for f in out["by_family"].values())


def test_the_figure_states_the_limit_of_its_own_interval():
    out = false_positive_rate(_corpus(CALIBRATION), Redactor())
    assert "sampling variance only" in out["interval_caveat"]
    assert "hand-authored" in out["interval_caveat"]
    assert out["half"] == CALIBRATION and out["k"] == Redactor().k
