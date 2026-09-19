"""F1: calibrate the matcher on real language before any volume is measured.

WHY THIS BLOCKS PHASE B. The phase A bench measured false strong attributions over fragments that
were keyed digests: forty bytes of material that exists nowhere else in the universe. That is the
most favourable input the matcher will ever see, and zero false attributions over it says the
plumbing is sound. It says nothing about the case phase B actually presents, which is natural
language and URLs that share structure: the same API, the same JSON shape, the same path prefix,
ordinary English words. Measuring volume with an uncalibrated matcher multiplies noise instead of
reducing it, and "the error margin is tiny" would be an adjective rather than a figure.

So this module answers one question with a number: **how often does the matcher affirm a
coincidence where there is none?**

THE FALSE POSITIVE, DEFINED EXACTLY. Take two calls, A and B, that are in flight at the same time
and share no information. A's request goes out. The matcher asks, per in-flight call, whether a
k-gram of that call's arguments appears in the request; that per-call question is what separates
CONTENT_UNIQUE from CONTENT_AMBIGUOUS in the addon. If the answer is yes for B, the matcher has
implicated a call that did not cause the request. That is a false positive, and it is the same
event whether the shared bytes came from a JSON key or from the word "deployment": in both cases
the evidence points at a call that had nothing to do with the transfer.

THE HOLDOUT, AND WHY IT IS ENFORCED IN CODE. All three F1 pieces are measured against this one
corpus, so the obvious failure is to tune the matcher until the corpus is happy and then publish
the corpus's own opinion of the matcher. The corpus is therefore split in two halves before any
measurement exists. The calibration half is for tuning: the k sweep and the rarity threshold are
chosen against it. The held-out half is touched once, at the end, and is what gets published.
``load_negative`` refuses to hand the held-out half to a caller that declares a calibration
purpose, and every tuning function asserts on the half it was given, so using the holdout to tune
is a raised exception rather than a lapse of memory. tests/test_negative_corpus.py fails if the
guard is removable.

Standard library only, like the rest of the measurement core.

ON THE CONFIDENCE INTERVAL, because this repository forbids dressing a deterministic quantity in
statistics (CLAUDE.md). The false-positive COUNT is exact: a k-gram either is or is not present,
and re-running the command gives the same integer. The interval is not about that count, it is
about generalising from these pairs to realistic pairs in general, which is a genuinely
inferential step, so a binomial interval is the honest way to report it. Its limit is stated with
it: the pairs are hand-authored, not drawn at random from any population, so the interval covers
sampling variance ONLY and says nothing about how representative the corpus is. That part is
argued in prose in docs/CALIBRATION.md, where an argument belongs.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from . import match as _match
from .driver import args_bytes
from .redact import Redactor

NEGATIVE_DIR = "corpus/negative"

# The two halves. The held-out filename appears in exactly one place in the source tree, here, so
# that a source scan can prove no tuning path reaches for it (tests/test_negative_corpus.py).
CALIBRATION = "calibration"
HELD_OUT = "held_out"
HALVES = (CALIBRATION, HELD_OUT)
_FILENAMES = {CALIBRATION: "calibration.json", HELD_OUT: "held-out.json"}
# The reserved half's filename, exported so that code which must REFUSE it (rarity.py checking that
# it never became a background document) can do so without writing the name a second time. A second
# literal would defeat the source scan in tests/test_negative_corpus.py, which is what proves no
# tuning path reaches for this file at all.
HELD_OUT_FILENAME = _FILENAMES[HELD_OUT]

# What a caller is going to do with the corpus. Not decoration: the loader refuses one combination.
PURPOSE_CALIBRATION = "calibration"   # choosing k, choosing a threshold, trying something out
PURPOSE_PUBLICATION = "publication"   # measuring the figure that gets published, once, at the end
PURPOSES = (PURPOSE_CALIBRATION, PURPOSE_PUBLICATION)


class HeldOutViolation(Exception):
    """Raised when the reserved half is asked for by something that is tuning.

    Its own exception type so a test can assert the refusal rather than pattern-match a message,
    and so nobody can mistake it for a missing file.
    """


@dataclass(frozen=True)
class NegativeCall:
    call_id: str
    family: str
    arguments: dict
    target: bytes
    body: bytes
    information: tuple[str, ...]


@dataclass(frozen=True)
class NegativeCorpus:
    half: str
    path: str
    families: tuple[str, ...]
    calls: tuple[NegativeCall, ...]

    def pairs(self) -> list[tuple[NegativeCall, NegativeCall]]:
        """Ordered pairs WITHIN a family: (A, B) asks if B's arguments appear in A's request.

        Within a family only, and that is a deliberate restriction rather than a convenience.
        Pairs drawn across families share nothing but the alphabet, so they are trivially negative,
        and including them would deflate the published rate with cases nobody finds hard. Ordered,
        because the question is asymmetric: B's arguments against A's request is not the same event
        as A's arguments against B's request, and both are real.
        """
        out = []
        for fam in self.families:
            members = [c for c in self.calls if c.family == fam]
            for a in members:
                for b in members:
                    if a.call_id != b.call_id:
                        out.append((a, b))
        return out


def load_negative(half: str, *, purpose: str, root: str | Path = ".") -> NegativeCorpus:
    """Load one half of the negative corpus. Refuses the holdout to a calibration purpose.

    The refusal is the point of this function existing at all instead of a bare json.load.
    """
    if half not in HALVES:
        raise ValueError(f"half must be one of {HALVES}, got {half!r}")
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}, got {purpose!r}")
    if half == HELD_OUT and purpose == PURPOSE_CALIBRATION:
        raise HeldOutViolation(
            "the held-out half may not be used for calibration. It is measured once, at the end, "
            "and is what the published figure comes from; tuning against it would publish the "
            "corpus's own opinion of the matcher (docs/CALIBRATION.md)")

    path = Path(root) / NEGATIVE_DIR / _FILENAMES[half]
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("half") != half:
        raise ValueError(f"{path} declares half {data.get('half')!r}, expected {half!r}")
    calls: list[NegativeCall] = []
    families: list[str] = []
    for fam in data["families"]:
        families.append(fam["family"])
        for c in fam["calls"]:
            calls.append(NegativeCall(
                call_id=c["id"], family=fam["family"], arguments=c["arguments"],
                target=c["request"]["target"].encode(), body=c["request"]["body"].encode(),
                information=tuple(c["information"]),
            ))
    return NegativeCorpus(half=half, path=str(path), families=tuple(families),
                          calls=tuple(calls))


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, at 95% by default.

    Wilson rather than the normal approximation because the rate here can be at or near zero, and
    the normal interval at zero successes is [0, 0], which asserts certainty from absence of
    evidence. Wilson gives an upper bound that shrinks with n instead, which is the honest reading
    of "we saw none in 224 pairs". Rejected Clopper-Pearson (exact) only because it needs the beta
    quantile and this module is standard-library-only; the difference at these n is immaterial and
    Wilson is the conservative-enough choice, not the convenient one.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo, hi = centre - half, centre + half
    # The endpoints at p = 0 and p = 1 are exactly 0 and 1 analytically (the variance term
    # vanishes and the algebra cancels), and floating point lands a few 1e-16 short: a test
    # asserting that the interval brackets the observed rate failed at 10 of 10 with an upper
    # bound of 0.9999999999999999. Snapped here rather than tolerated in the test, because the
    # exact value is known and a test written around float noise hides the next real error.
    if successes == 0:
        lo = 0.0
    if successes == n:
        hi = 1.0
    return (max(0.0, lo), min(1.0, hi))


def claims_match(a: NegativeCall, b: NegativeCall, redactor: Redactor, decide=None) -> bool:
    """Does the matcher affirm that B's arguments appear in A's request?

    This is the addon's own per-call question (capture_addon.request), run directly, so the figure
    describes the matcher that ships and not a reimplementation of it.

    ``decide`` replaces that question with another predicate over the same inputs, which is how the
    F1.3 rarity experiment is measured without the matcher gaining a parameter it does not ship
    with. Default None means the shipped matcher, and every figure says which it used.
    """
    digests = frozenset(redactor.kgram_digest_set(args_bytes(b.arguments)))
    if decide is not None:
        return decide(a.target, a.body, digests, redactor)
    return _match.match_request(a.target, a.body, {}, digests, redactor).causal


def false_positive_rate(corpus: NegativeCorpus, redactor: Redactor, decide=None,
                        weighting: str = "") -> dict:
    """The F1.1 figure: how often the matcher claims a coincidence that does not exist.

    Reported per family as well as pooled, because the families are deliberately not equivalent:
    one of them exists to be the worst realistic case and one exists to be a good one, and a
    pooled rate alone would hide which shapes are dangerous. A reader deciding whether to trust an
    attribution needs the shape, not the average over our choice of shapes.
    """
    pairs = corpus.pairs()
    by_family: dict[str, dict] = {}
    total_fp = 0
    for a, b in pairs:
        fam = by_family.setdefault(a.family, {"pairs": 0, "false_positives": 0})
        fam["pairs"] += 1
        if claims_match(a, b, redactor, decide):
            fam["false_positives"] += 1
            total_fp += 1
    for fam in by_family.values():
        lo, hi = wilson_interval(fam["false_positives"], fam["pairs"])
        fam["rate"] = round(fam["false_positives"] / fam["pairs"], 4) if fam["pairs"] else 0.0
        fam["wilson_95"] = [round(lo, 4), round(hi, 4)]

    n = len(pairs)
    lo, hi = wilson_interval(total_fp, n)
    return {
        "name": "matcher_false_positive_rate_on_structured_language",
        "half": corpus.half,
        "k": redactor.k,
        # Named rather than boolean: "which decision produced this rate" has more than two answers
        # now, and a figure that only said True/False could not be told apart from the next variant.
        "decision": weighting or "shipped_matcher",
        "rarity_weighting": bool(weighting),
        "pairs": n,
        "false_positives": total_fp,
        "rate": round(total_fp / n, 4) if n else 0.0,
        "wilson_95": [round(lo, 4), round(hi, 4)],
        "by_family": by_family,
        "what_a_pair_is": ("two calls in flight at once, from the same family, sharing language "
                           "structure and no information. A false positive is the matcher finding "
                           "a k-gram of one call's arguments in the other call's request"),
        "interval_caveat": ("the count is exact and deterministic; the interval covers sampling "
                           "variance only. These pairs are hand-authored, not drawn at random "
                           "from any population, so the interval says nothing about how "
                           "representative the corpus is (docs/CALIBRATION.md)"),
        "command": "make fp" if corpus.half == HELD_OUT else "make fp-calibration",
    }


# =================================================================================================
# F1.2: the k sweep.
#
# k = 16 was chosen by judgement. This section replaces the judgement with a curve, over three
# quantities that have to be read together, because each one alone picks a different k:
#
#   FALSE POSITIVES, on the calibration half. Falls as k grows: a longer run is harder to share by
#   accident. Alone it would choose the largest k available.
#
#   BENCH DETECTION RECALL, on the phase A transfers the bench designed to be detectable. This is
#   the truth pattern F1.2 was told to protect. It holds until k passes the length of the bench's
#   fragments and then collapses. Alone it would choose the smallest k available.
#
#   SELF-MATCH RECALL, on the negative corpus itself: can the matcher still find a call's own
#   arguments in that call's OWN request? It is the same question as bench recall asked of realistic
#   material instead of keyed digests, and it is here because the bench's fragments are forty bytes
#   BY DESIGN. "Recall does not sink until k > 40" is a fact about the bench, not evidence that a
#   large k is safe: a real fragment shorter than k is invisible at that k, and this curve is the
#   only place that cost shows up.
#
# The choice rule is written before the numbers (choose_k) so the constant is the output of a rule
# rather than a preference: among the k values that keep bench recall at its maximum, take those
# with the lowest false-positive rate, and break the tie toward the SMALLEST k, because every byte
# of k is a false negative on some real fragment.
# =================================================================================================

# The sweep range F1.2 was given. Every integer, not a coarse step: the interesting behaviour is a
# knee, and a step of four can step straight over it.
K_MIN, K_MAX = 8, 64

POSITIVE_PATH = "corpus/positive/bench-transfers.json"

# Channels the matcher reads. A transfer in any other channel is a known negative by design
# (negative 3): a header or a re-encoded body carries no literal run to find.
READABLE_CHANNELS = ("target", "body")


@dataclass(frozen=True)
class PositiveTransfer:
    """One transfer the phase A bench actually made, with the bytes it sent."""
    transfer_id: str
    channel: str
    arguments: dict
    target: bytes
    body: bytes
    detectable_by_design: bool
    not_detectable_reason: str


def load_positive(path: str | Path = POSITIVE_PATH, root: str | Path = ".") -> list[PositiveTransfer]:
    """Load the phase A positive control: what the bench sent, distilled from its own ledger."""
    data = json.loads((Path(root) / path).read_text(encoding="utf-8"))
    import base64
    return [PositiveTransfer(
        transfer_id=t["transfer_id"], channel=t["channel"], arguments=t["arguments"],
        target=t["target"].encode(), body=base64.b64decode(t["body_b64"]),
        detectable_by_design=t["detectable_by_design"],
        not_detectable_reason=t.get("not_detectable_reason", ""),
    ) for t in data["transfers"]]


def detection_recall(transfers: list[PositiveTransfer], redactor: Redactor) -> dict:
    """Of the transfers the bench MEANT to be detectable, how many does the matcher find at this k.

    Reported with the mirror figure, how many known negatives it found, which must stay zero: a
    sweep that improved recall by starting to "detect" a gzipped payload would be reporting a
    collision as a success.
    """
    detectable = [t for t in transfers if t.detectable_by_design]
    negatives = [t for t in transfers if not t.detectable_by_design]

    def found(t: PositiveTransfer) -> bool:
        digests = frozenset(redactor.kgram_digest_set(args_bytes(t.arguments)))
        return _match.match_request(t.target, t.body, {}, digests, redactor).causal

    detected = sum(1 for t in detectable if found(t))
    leaked_by_reason: dict[str, int] = {}
    for t in negatives:
        if found(t):
            leaked_by_reason[t.not_detectable_reason or "unclassified"] = \
                leaked_by_reason.get(t.not_detectable_reason or "unclassified", 0) + 1
    by_reason: dict[str, int] = {}
    for t in negatives:
        by_reason[t.not_detectable_reason or "unclassified"] = \
            by_reason.get(t.not_detectable_reason or "unclassified", 0) + 1
    return {
        "detectable_by_design": len(detectable),
        "detected": detected,
        "recall": round(detected / len(detectable), 4) if detectable else 0.0,
        # Split by WHY a transfer could not be detected. "channel_not_read" and "re_encoded" are
        # what negative 3 costs; "nothing_carried" is a transfer with no material in it, which is a
        # different fact and would inflate the known-negative figure if pooled with them.
        "not_detectable": by_reason,
        "known_negatives_detected": sum(leaked_by_reason.values()),
        "known_negatives_detected_by_reason": leaked_by_reason,
    }


def self_match_recall(corpus: NegativeCorpus, redactor: Redactor) -> dict:
    """Can the matcher find a call's own arguments in that call's own request, on realistic material.

    The true-positive question asked of the same corpus the false-positive rate comes from, so the
    two curves are over identical material and the trade-off between them is real rather than an
    artefact of two different fixtures.
    """
    per_family: dict[str, dict] = {}
    for call in corpus.calls:
        fam = per_family.setdefault(call.family, {"calls": 0, "matched": 0})
        fam["calls"] += 1
        if claims_match(call, call, redactor):
            fam["matched"] += 1
    for fam in per_family.values():
        fam["recall"] = round(fam["matched"] / fam["calls"], 4) if fam["calls"] else 0.0
    total = sum(f["calls"] for f in per_family.values())
    matched = sum(f["matched"] for f in per_family.values())
    return {"calls": total, "matched": matched,
            "recall": round(matched / total, 4) if total else 0.0,
            "by_family": per_family}


def choose_k(rows: list[dict]) -> dict:
    """The rule, written before the numbers were looked at. Returns the chosen k and the reasoning.

    1. Keep only the k values whose bench detection recall equals the best recall observed anywhere
       in the sweep. That is "without sinking the phase A recall", read strictly: not "close to",
       equal to the best the truth pattern allows.
    2. Among those, keep the lowest false-positive rate.
    3. Break the remaining tie toward the SMALLEST k. Every additional byte of k is a false negative
       on some real fragment shorter than it, and a false negative is the safe direction only as long
       as it is not bought for nothing.

    A k that lets a known negative be "detected" is disqualified outright, whatever its rate: that
    would be a collision counted as a success.
    """
    eligible = [r for r in rows if r["bench"]["known_negatives_detected"] == 0]
    if not eligible:
        return {"chosen_k": None, "reason": "every k detected a known negative; the sweep is broken"}
    best_recall = max(r["bench"]["recall"] for r in eligible)
    keep = [r for r in eligible if r["bench"]["recall"] == best_recall]
    best_fp = min(r["false_positives"]["rate"] for r in keep)
    keep = [r for r in keep if r["false_positives"]["rate"] == best_fp]
    chosen = min(keep, key=lambda r: r["k"])
    return {
        "chosen_k": chosen["k"],
        "rule": ("keep the k values at the best observed bench recall, take the lowest "
                 "false-positive rate among them, break ties toward the smallest k"),
        "bench_recall_at_choice": best_recall,
        "false_positive_rate_at_choice": best_fp,
        "self_match_recall_at_choice": chosen["self_match"]["recall"],
        "candidates_at_the_same_rate": sorted(r["k"] for r in keep),
    }


def sweep_k(corpus: NegativeCorpus, transfers: list[PositiveTransfer],
            k_min: int = K_MIN, k_max: int = K_MAX, salt: bytes | None = None) -> dict:
    """The F1.2 curve. Refuses the held-out half: choosing k is calibration.

    The guard is here as well as in the loader, deliberately. A caller could load the held-out half
    for publication, legitimately, and then hand it to this function, and the loader would never
    know. Two checks because there are two ways in.
    """
    if corpus.half != CALIBRATION:
        raise HeldOutViolation(
            f"sweep_k is calibration: it may not run on the {corpus.half} half. The reserved half "
            f"is measured once, at the end, and never used to choose a parameter")

    rows = []
    for k in range(k_min, k_max + 1):
        redactor = Redactor(salt=salt, k=k) if salt else Redactor(k=k)
        fp = false_positive_rate(corpus, redactor)
        rows.append({
            "k": k,
            "false_positives": {"pairs": fp["pairs"], "count": fp["false_positives"],
                                "rate": fp["rate"], "wilson_95": fp["wilson_95"],
                                "by_family": {f: d["rate"] for f, d in fp["by_family"].items()}},
            "self_match": self_match_recall(corpus, redactor),
            "bench": detection_recall(transfers, redactor),
        })
    return {
        "name": "k_sweep",
        "half": corpus.half,
        "k_range": [k_min, k_max],
        "curve": rows,
        "choice": choose_k(rows),
        "what_each_curve_is": {
            "false_positives": ("pairs of concurrent calls sharing structure and no information "
                                "where the matcher claims a match anyway; lower is better"),
            "self_match": ("whether a call's own arguments are found in its own request, on the "
                           "same realistic material; the cost of a larger k, and the curve the "
                           "bench cannot show because its fragments are 40 bytes by design"),
            "bench": ("phase A transfers the bench designed to be detectable; the truth pattern. "
                      "known_negatives_detected must stay at zero, or a collision is being counted "
                      "as a success"),
        },
        "command": "make ksweep",
    }


# =================================================================================================
# The self-match ceiling, and the inventory that explains it.
#
# The self-match figure is the number that bounds everything phase B publishes, and it was buried in
# a column of the k sweep. It deserves its own definition and its own decomposition, because a
# reader who sees 0.5 needs to know three things that the number alone does not say: what exactly was
# measured, over which corpus, and WHY the other half fails. Without the third, "half the material
# does not self-match" reads as a defect to fix rather than as the limit it is.
#
# WHAT SELF-MATCH IS, exactly. For one call, take the bytes the matcher would index on the cause side
# (driver.args_bytes of its arguments, which is what the driver publishes) and the bytes of the
# request that same call caused (its declared target and body). Ask the shipped matcher whether any
# k-gram of the first appears in the second. It is the true-positive question in its easiest possible
# form: the call is its own cause, there are no competing candidates, and nothing is concurrent. A
# call that fails HERE can never be attributed by content anywhere.
#
# WHAT IT IS NOT. It is not recall against real servers: the requests are the negative corpus's
# declared ones (docs/CALIBRATION.md says how they are re-derived in tests), so this measures the
# matcher against realistic ARGUMENT SHAPES, not against the wire behaviour of ten real servers. A
# real server that percent-encodes differently, reorders fields or wraps the payload moves it.
# =================================================================================================


def longest_common_run(a: bytes, b: bytes) -> int:
    """Length of the longest byte run present in both. Exact, no heuristics.

    Quadratic in the inputs, which is fine at these sizes (arguments and request lines are hundreds
    of bytes) and it is the honest way to answer "how close did this get to the threshold": a k-gram
    check only ever answers yes or no, and the interesting fact about a miss is by how much it
    missed. Rolling two rows so the memory stays linear.
    """
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def detectability_inventory(corpus: NegativeCorpus, transfers: list[PositiveTransfer],
                            redactor: Redactor, bait_dir: str | Path = "corpus/context",
                            root: str | Path = ".") -> dict:
    """Why the self-match figure is what it is, over three populations and two thresholds.

    The two thresholds are different guarantees and conflating them would overstate what is safe:

      k                 a run this long IS found, because numbers 4 and 5 match exact k-grams.
      w + k - 1         a run this long is ALSO guaranteed to survive winnowing, which is what the
                        persisted, digest-only fingerprints use (shingle.py). Between the two, a
                        match enters the numbers but may not be reconstructible later from what was
                        kept on disk.

    The three populations are not interchangeable either. The planted bait is material we control and
    sized on purpose; the realistic arguments are the population the self-match figure is measured
    over; the phase A transfers are the keyed digests, present as the contrast that shows how far
    from realistic the bench's own material is.
    """
    import re

    floor_exact = redactor.k
    floor_winnowed = redactor.k + redactor.w - 1

    def bucket(run: int) -> str:
        if run >= floor_winnowed:
            return "at_or_above_winnowing_floor"
        if run >= floor_exact:
            return "matched_but_below_winnowing_floor"
        return "below_k_invisible"

    # 1. The planted bait: every CANARY_ token in the context files, by length.
    bait: dict[str, list[int]] = {}
    for path in sorted((Path(root) / bait_dir).rglob("*")):
        if not path.is_file():
            continue
        for tok in re.findall(r"CANARY_[A-Za-z0-9_.:@/-]+",
                              path.read_text(errors="replace")):
            bait.setdefault(bucket(len(tok)), []).append(len(tok))
    bait_counts = {b: len(v) for b, v in sorted(bait.items())}

    # 2. The realistic arguments: the longest run each call shares with its OWN request, which is
    #    the quantity self-match thresholds. Per family, because the families fail for different
    #    reasons and a pooled figure hides which.
    families: dict[str, dict] = {}
    for call in corpus.calls:
        run = longest_common_run(args_bytes(call.arguments), call.target + b"\x00" + call.body)
        fam = families.setdefault(call.family, {"calls": 0, "self_matched": 0, "runs": [],
                                                "buckets": {}})
        fam["calls"] += 1
        fam["runs"].append(run)
        fam["buckets"][bucket(run)] = fam["buckets"].get(bucket(run), 0) + 1
        if claims_match(call, call, redactor):
            fam["self_matched"] += 1
    for fam in families.values():
        runs = sorted(fam.pop("runs"))
        fam["longest_common_run"] = {"min": runs[0], "median": runs[len(runs) // 2],
                                     "max": runs[-1]}
        fam["self_match_recall"] = round(fam["self_matched"] / fam["calls"], 4)

    # 3. The phase A transfers, as the contrast.
    bench_runs = sorted(longest_common_run(args_bytes(t.arguments), t.target + b"\x00" + t.body)
                        for t in transfers if t.detectable_by_design)
    bench_buckets: dict[str, int] = {}
    for run in bench_runs:
        bench_buckets[bucket(run)] = bench_buckets.get(bucket(run), 0) + 1

    overall = self_match_recall(corpus, redactor)
    return {
        "name": "detectability_inventory",
        "k": redactor.k,
        "w": redactor.w,
        "floor_exact_kgram_match": floor_exact,
        "floor_winnowing_guarantee": floor_winnowed,
        "what_self_match_is": (
            "for one call, whether any k-gram of driver.args_bytes(its arguments) appears in the "
            "request that same call caused. The true-positive question in its easiest form: the "
            "call is its own cause, there is no competing candidate and nothing is concurrent. A "
            "call that fails here can never be attributed by content anywhere"),
        "measured_over": corpus.path,
        "planted_bait_by_bucket": bait_counts,
        "realistic_arguments": {
            "self_match_recall": overall["recall"],
            "calls": overall["calls"],
            "matched": overall["matched"],
            "by_family": families,
        },
        "phase_a_transfers_for_contrast": {
            "transfers": len(bench_runs),
            "by_bucket": bench_buckets,
            "longest_common_run": ({"min": bench_runs[0], "median": bench_runs[len(bench_runs) // 2],
                                    "max": bench_runs[-1]} if bench_runs else {}),
        },
        "why_this_is_a_ceiling": (
            "an attributable share measured by a sensor that cannot see half of the realistic "
            "material it is shown is at most half of the true share. Number 5 is therefore "
            "published as a LOWER BOUND, and this figure is the reason (docs/THREATS.md)"),
        "command": "make inventory",
    }
