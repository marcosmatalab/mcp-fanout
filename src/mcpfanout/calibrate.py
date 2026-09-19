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


def claims_match(a: NegativeCall, b: NegativeCall, redactor: Redactor) -> bool:
    """Does the matcher affirm that B's arguments appear in A's request?

    This is the addon's own per-call question (capture_addon.request), run directly, so the figure
    describes the matcher that ships and not a reimplementation of it.
    """
    digests = frozenset(redactor.kgram_digest_set(args_bytes(b.arguments)))
    return _match.match_request(a.target, a.body, {}, digests, redactor).causal


def false_positive_rate(corpus: NegativeCorpus, redactor: Redactor) -> dict:
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
        if claims_match(a, b, redactor):
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
