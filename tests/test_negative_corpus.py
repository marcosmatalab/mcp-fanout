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


# The k the corpus was authored against, which is NOT the shipped constant and must not follow it.
# The corpus's job is to contain the structural overlap real APIs have; whether that overlap
# survives the shipped k is the thing being MEASURED (docs/CALIBRATION.md, F1.2 moved k from 16 to
# 22 precisely because it stops surviving there). A test that demanded overlap at the shipped k
# would fail as a direct consequence of the sweep succeeding, which is a test asserting the
# opposite of the result.
AUTHORING_K = 16


@pytest.mark.parametrize("half", [CALIBRATION, HELD_OUT])
def test_the_arguments_of_a_family_overlap_at_the_authoring_k(half):
    """Structure has to be shared at a granularity the matcher can work at, not just visibly.

    The mirror of the bench's precondition (tests/test_bench_metrics.py fails if two bench fragments
    share a k-gram), asked at AUTHORING_K: at least one pair per family must share a run of that
    length, or the family is not exercising the thing it exists to exercise and a rate of zero would
    mean nothing.
    """
    r = Redactor(salt=b"negative-corpus-structure-check", k=AUTHORING_K)
    corpus = _corpus(half)
    for fam in corpus.families:
        members = [c for c in corpus.calls if c.family == fam]
        sets = [r.kgram_digest_set(args_bytes(c.arguments)) for c in members]
        sharing = any(sets[i] & sets[j] for i in range(len(sets)) for j in range(i + 1, len(sets)))
        assert sharing, f"{fam}: no two calls share a {AUTHORING_K}-byte run in their arguments"


def test_the_registry_and_the_shipped_constant_agree_on_k():
    """A capture matching at a k no published figure describes would fail silently, not loudly.

    Three places used to carry the value: the constant, the registry, and a literal in run.sh. The
    literal is gone (run.sh reads the constant) and this pins the remaining two together, because a
    registry k that drifted would give the capture a different matcher from the one every
    calibration figure in docs/ was measured with.
    """
    import yaml
    from mcpfanout.shingle import DEFAULT_K, DEFAULT_W
    registry = yaml.safe_load((REPO / "registry" / "servers.yaml").read_text())
    assert registry["k"] == DEFAULT_K, (registry["k"], DEFAULT_K)
    assert registry["w"] == DEFAULT_W, (registry["w"], DEFAULT_W)
    run_sh = (REPO / "harness" / "run.sh").read_text()
    assert "MCPFANOUT_K=\"16\"" not in run_sh and "MCPFANOUT_K=\"22\"" not in run_sh, (
        "run.sh is carrying a literal k again")


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


# --- F1.2: the sweep, its guard, and the positive control it measures recall against.

def test_the_sweep_refuses_the_reserved_half_even_when_it_is_handed_over_loaded():
    """Two ways in, two checks. The loader cannot see what a caller does with what it returned.

    Loading the reserved half for publication is legitimate. Handing that object to a function whose
    job is choosing a parameter is not, and the loader would never know, so sweep_k checks the half
    it was given.
    """
    from mcpfanout.calibrate import HeldOutViolation, load_positive, sweep_k
    held = load_negative(HELD_OUT, purpose=PURPOSE_PUBLICATION, root=REPO)
    with pytest.raises(HeldOutViolation):
        sweep_k(held, load_positive(root=REPO), k_min=16, k_max=17)


def test_the_positive_control_carries_the_bench_transfers_and_says_which_run_it_came_from():
    """Recall needs a denominator we caused on purpose, and the fixture has to name its source."""
    from mcpfanout.calibrate import load_positive
    data = json.loads((REPO / "corpus" / "positive" / "bench-transfers.json").read_text())
    assert data["source_run"], "the fixture does not say which bench run produced it"
    assert "gate rule 4" in data["_why_committed"], "the fixture does not justify being committed"

    transfers = load_positive(root=REPO)
    assert len(transfers) >= 60
    detectable = [t for t in transfers if t.detectable_by_design]
    negatives = [t for t in transfers if not t.detectable_by_design]
    assert detectable and negatives, "a sweep needs both, or it cannot show a collision"
    # Detectability is the BENCH's design decision, never the matcher's opinion, and there are
    # three cases: a channel the matcher reads carrying material, a channel it cannot read, and a
    # transfer that carried nothing at all. The third is not what negative 3 costs and must not be
    # pooled with the second.
    for t in detectable:
        assert t.channel in ("target", "body") and t.not_detectable_reason == "", t
    reasons = {t.not_detectable_reason for t in negatives}
    assert reasons == {"channel_not_read", "re_encoded", "nothing_carried"}, reasons
    for t in negatives:
        if t.not_detectable_reason == "channel_not_read":
            assert t.channel == "header"
        elif t.not_detectable_reason == "re_encoded":
            assert t.channel.startswith("body:")
        else:
            assert t.channel == "none"


def test_every_positive_transfer_carries_the_arguments_that_caused_it():
    """Without the arguments there is no cause side, and recall would have nothing to compute."""
    from mcpfanout.calibrate import load_positive
    for t in load_positive(root=REPO):
        assert t.arguments, f"{t.transfer_id} has no arguments"
        assert t.target or t.body, f"{t.transfer_id} carries neither target nor body"


def test_the_bench_transfers_are_detected_at_the_shipped_k_and_the_known_negatives_are_not():
    """The truth pattern, asserted at the constant we ship rather than only inside the sweep.

    If this failed, gate rule 8's committed instrument artifact would describe a matcher other than
    the one in the repository.
    """
    from mcpfanout.calibrate import detection_recall, load_positive
    out = detection_recall(load_positive(root=REPO), Redactor())
    assert out["recall"] == 1.0, out
    assert out["known_negatives_detected"] == 0, out


def test_the_choice_rule_prefers_the_smallest_k_among_equals():
    """The tie-break is the whole reason a rule is written down instead of a value being picked.

    Every byte of k is a false negative on some real fragment, so among k values that are
    indistinguishable on false positives and on recall, the smallest wins. Checked on a synthetic
    curve so the assertion is about the rule and not about this month's data.
    """
    from mcpfanout.calibrate import choose_k
    rows = [
        {"k": 10, "false_positives": {"rate": 0.3}, "bench": {"recall": 1.0, "known_negatives_detected": 0},
         "self_match": {"recall": 0.9}},
        {"k": 20, "false_positives": {"rate": 0.0}, "bench": {"recall": 1.0, "known_negatives_detected": 0},
         "self_match": {"recall": 0.6}},
        {"k": 30, "false_positives": {"rate": 0.0}, "bench": {"recall": 1.0, "known_negatives_detected": 0},
         "self_match": {"recall": 0.3}},
        {"k": 40, "false_positives": {"rate": 0.0}, "bench": {"recall": 0.5, "known_negatives_detected": 0},
         "self_match": {"recall": 0.2}},
    ]
    out = choose_k(rows)
    assert out["chosen_k"] == 20, out
    assert out["candidates_at_the_same_rate"] == [20, 30]


def test_the_choice_rule_will_not_take_a_k_that_detects_a_known_negative():
    """A k that "detects" a gzipped payload is reporting a collision as a success."""
    from mcpfanout.calibrate import choose_k
    rows = [
        {"k": 8, "false_positives": {"rate": 0.0}, "bench": {"recall": 1.0, "known_negatives_detected": 2},
         "self_match": {"recall": 0.9}},
        {"k": 22, "false_positives": {"rate": 0.1}, "bench": {"recall": 1.0, "known_negatives_detected": 0},
         "self_match": {"recall": 0.5}},
    ]
    assert choose_k(rows)["chosen_k"] == 22


def test_the_choice_rule_reports_failure_rather_than_picking_something():
    from mcpfanout.calibrate import choose_k
    rows = [{"k": 8, "false_positives": {"rate": 0.0},
             "bench": {"recall": 1.0, "known_negatives_detected": 1}, "self_match": {"recall": 0.9}}]
    out = choose_k(rows)
    assert out["chosen_k"] is None and "broken" in out["reason"]


def test_the_shipped_k_is_the_one_the_committed_curve_chose():
    """The constant is the output of the rule, or the citation beside it is decoration."""
    from mcpfanout.shingle import DEFAULT_K
    curve = json.loads((REPO / "docs" / "figures" / "calibration" /
                        "ksweep-calibration.json").read_text())
    assert curve["choice"]["chosen_k"] == DEFAULT_K, (curve["choice"], DEFAULT_K)
    assert curve["half"] == CALIBRATION, "the published curve was computed on the reserved half"
