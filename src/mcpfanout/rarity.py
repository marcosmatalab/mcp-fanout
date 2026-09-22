"""F1.3: weight a k-gram by how common it is, and require a minimum rarity mass to claim a match.

THE PROBLEM, stated as F1.3 was given it. Twenty-two bytes of `{"locale": "en-US", ` appear in every
call of an API and are worth nothing. Twenty-two bytes of a token are worth everything. The matcher
weighs them the same, so a match is affirmed on shared boilerplate exactly as readily as on shared
payload, and the F1.1 measurement at k = 16 priced that: one family of the negative corpus failed 56
of 56 pairs on nothing but its envelope.

THIS DOES NOT BREAK NEGATIVE 3. Counting how many documents a byte sequence occurs in is a fact
about
occurrence, not an inference about meaning. Nothing here paraphrases, embeds, classifies or asks a
model what a fragment is; a k-gram's weight is 1/(1 + df), an arithmetic function of a count. It is
the suppression of common substrings that commercial IDM has done for fifteen years, and it is the
same kind of operation as the exclusion list in `classify.py`: a declared, published, versioned
statement that some observations carry no information, applied the same way to every run.

WHERE THIS CODE IS NOT. It is deliberately NOT in the matching path. `match.py` has no rarity
parameter and the capture addon does not know this module exists. The acceptance criterion F1.3 was
given is a number, not a story: the false-positive rate is re-measured with weighting on and must
fall, and if it does not the weighting is reverted rather than kept because it is more
sophisticated.
It did not fall, for the reasons written in docs/CALIBRATION.md, so what survives is this module,
the
command that re-derives the comparison, and the written verdict. A reader who wants to switch it on
has the mechanism and the evidence; nobody gets it switched on by default on the strength of it
sounding advanced.

THE DECISION IT IMPLEMENTS. A match is affirmed only when the matched k-grams carry at least
MIN_RARITY_MASS between them, where each contributes 1/(1 + df) and df is the number of background
documents it appears in. A k-gram absent from the background contributes a full 1.0; one appearing
in
half the documents of a 32-document corpus contributes 0.06. The default threshold of 1.0 therefore
reads as "the evidence must amount to at least one run of bytes this background has never seen".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import match as _match
from .calibrate import HELD_OUT_FILENAME as _HELD_OUT_FILENAME
from .redact import Redactor

BACKGROUND_SOURCES = "corpus/background/sources.json"

# The threshold, in units of "one k-gram never seen in the background". Calibrated on the
# calibration
# half only (docs/CALIBRATION.md, F1.3); a threshold chosen against the reserved half would be the
# holdout being used to tune, which is what calibrate.load_negative exists to refuse.
MIN_RARITY_MASS = 1.0

# The one file that may never be a background document. Imported rather than spelled out: the source
# scan in tests/test_negative_corpus.py proves that no module outside the loader names the reserved
# half, and a literal here would be a hole in that proof even though this use is a refusal.
FORBIDDEN_BACKGROUND = _HELD_OUT_FILENAME


class BackgroundLeak(Exception):
    """Raised when the evaluation half is found among the background documents."""


@dataclass(frozen=True)
class RarityIndex:
    """Document frequency per k-gram digest, over a declared set of background documents."""
    k: int
    documents: int
    df: dict[str, int]
    sources: tuple[str, ...]
    sha256: str

    @classmethod
    def build(cls, redactor: Redactor, sources: str | Path = BACKGROUND_SOURCES,
              root: str | Path = ".") -> RarityIndex:
        """Build the index from the declared sources. Refuses to include the evaluation half.

        One document per FILE, and document frequency rather than raw occurrence count: a run of
        bytes repeated four hundred times inside one file is one document's worth of evidence that
        it
        is common, not four hundred. That is the standard choice and it is the conservative one
        here.
        """
        root = Path(root)
        spec = json.loads((root / sources).read_text(encoding="utf-8"))
        paths: list[Path] = []
        for pattern in spec["documents"]:
            if "*" in pattern:
                paths.extend(sorted(root.glob(pattern)))
            else:
                paths.append(root / pattern)
        for p in paths:
            if p.name == FORBIDDEN_BACKGROUND:
                raise BackgroundLeak(
                    f"{p} is the evaluation half of the negative corpus and may not be a "
                    "background "
                    f"document: weighting learned from it would be scored against itself")

        df: dict[str, int] = {}
        digest = hashlib.sha256()
        for p in paths:
            data = p.read_bytes()
            digest.update(data)
            for g in redactor.kgram_digest_set(data):
                df[g] = df.get(g, 0) + 1
        return cls(k=redactor.k, documents=len(paths), df=df,
                   sources=tuple(str(p.relative_to(root)) for p in paths),
                   sha256=digest.hexdigest())

    def weight(self, digest: str) -> float:
        """1 / (1 + document frequency). Unseen means 1.0; ubiquitous approaches zero."""
        return 1.0 / (1.0 + self.df.get(digest, 0))

    def mass(self, digests: Iterable[str]) -> float:
        return sum(self.weight(g) for g in digests)

    def citation(self) -> dict[str, Any]:
        """What goes into a published figure: counts and a digest, never a document's content."""
        return {"documents": self.documents, "k": self.k, "distinct_kgrams": len(self.df),
                "sources_sha256": self.sha256, "sources": list(self.sources)}


def claims_match_weighted(target: bytes, body: bytes, args_digests: frozenset[str],
                          redactor: Redactor, index: RarityIndex,
                          min_mass: float = MIN_RARITY_MASS) -> bool:
    """The weighted decision: a match needs enough rarity mass, not merely one shared k-gram.

    Built on `match.argument_kgrams_present`, the same function the shipped matcher uses to decide
    that anything matched at all, so the two cannot disagree about WHICH k-grams matched. The only
    new thing here is the predicate applied to them.
    """
    if index.k != redactor.k:
        raise ValueError(f"index built at k={index.k}, matcher at k={redactor.k}: a weight looked "
                         f"up at the wrong k is a weight for a different byte sequence")
    matched = (_match.argument_kgrams_present(target, args_digests, redactor)
               | _match.argument_kgrams_present(body, args_digests, redactor))
    # An empty intersection is never a match, whatever the threshold. Written as a bare
    # `mass >= min_mass` this affirmed a match on no evidence at all when min_mass was 0, which a
    # threshold sweep reaching down to zero would have walked straight into: the rate would have
    # jumped to 1.0 for a reason that has nothing to do with rarity.
    if not matched:
        return False
    return index.mass(matched) >= min_mass


# =================================================================================================
# The acceptance measurement, and the verdict it produces.
#
# F1.3's criterion is a number: re-measure the F1.1 rate with weighting on; if it does not fall, the
# weighting is reverted and why is documented. So the command below produces four things and a
# conclusion derived from them, rather than a conclusion illustrated by them:
#
#   1. the PUBLISHED comparison: unweighted against weighted on the held-out half, at the shipped k;
#   2. a MECHANISM PROBE at a k where false positives still exist, because a mechanism cannot be
#      shown to work or fail against a rate that is already zero;
#   3. the DOCUMENT FREQUENCY of the k-grams that actually collide, which is the difference between
#      "the technique does not work" and "our background corpus cannot see what is common";
#   4. a THRESHOLD SWEEP, because concluding from one threshold would be concluding from a guess.
# =================================================================================================

VERDICT_KEPT = "kept"
VERDICT_REVERTED = "reverted"

# The thresholds probed. Wide enough to reach the point where every false positive is suppressed, so
# that the cost of getting there is visible rather than argued about.
MASS_LADDER = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 16.0)


def _decider(index: RarityIndex, min_mass: float) -> Callable[..., bool]:
    def decide(target: bytes, body: bytes, args_digests: Iterable[str],
               redactor: Redactor) -> bool:
        return claims_match_weighted(target, body, frozenset(args_digests), redactor, index,
                                     min_mass)
    return decide


def colliding_kgram_frequencies(corpus: Any, redactor: Redactor,
                                index: RarityIndex) -> dict[str, Any]:
    """How common, in the background, are the k-grams that actually cause false positives.

    This is the measurement that separates two very different failures. If the colliding k-grams are
    frequent in the background, weighting them down is possible and a threshold can exploit it. If
    they are unseen, every one of them carries full weight, the threshold degenerates into "how many
    k-grams matched", and that is a length requirement wearing rarity's clothes.
    """
    from .driver import args_bytes
    by_df: dict[str, int] = {}
    per_pair: list[int] = []
    for a, b in corpus.pairs():
        digests = frozenset(redactor.kgram_digest_set(args_bytes(b.arguments)))
        matched = (_match.argument_kgrams_present(a.target, digests, redactor)
                   | _match.argument_kgrams_present(a.body, digests, redactor))
        if not matched:
            continue
        per_pair.append(len(matched))
        for g in matched:
            key = str(index.df.get(g, 0))
            by_df[key] = by_df.get(key, 0) + 1
    ordered = sorted(per_pair)
    return {
        "colliding_kgram_instances": sum(by_df.values()),
        "instances_by_document_frequency": dict(sorted(by_df.items(),
                                                    key=lambda kv: int(kv[0]))),
        "matched_kgrams_per_colliding_pair": {
            "pairs": len(ordered),
            "min": ordered[0] if ordered else 0,
            "median": ordered[len(ordered) // 2] if ordered else 0,
            "max": ordered[-1] if ordered else 0,
        },
        "background_documents": index.documents,
    }


def true_match_kgram_counts(transfers: Iterable[Any], redactor: Redactor) -> dict[str, Any]:
    """The same count for matches that ARE real, so the two distributions can be compared.

    A threshold can only separate false from true matches if the two differ on the quantity it
    thresholds. Publishing both distributions is what makes that checkable instead of assumed.
    """
    from .driver import args_bytes
    counts = []
    for t in transfers:
        if not t.detectable_by_design:
            continue
        digests = frozenset(redactor.kgram_digest_set(args_bytes(t.arguments)))
        matched = (_match.argument_kgrams_present(t.target, digests, redactor)
                   | _match.argument_kgrams_present(t.body, digests, redactor))
        if matched:
            counts.append(len(matched))
    ordered = sorted(counts)
    return {"transfers": len(ordered), "min": ordered[0] if ordered else 0,
            "median": ordered[len(ordered) // 2] if ordered else 0,
            "max": ordered[-1] if ordered else 0}


def sweep_mass(corpus: Any, transfers: Iterable[Any], redactor: Redactor, index: RarityIndex,
               masses: Iterable[float] = MASS_LADDER) -> list[dict[str, Any]]:
    """False positives and both recalls against the mass threshold. Calibration half only.

    Guarded like calibrate.sweep_k and for the same reason: choosing a threshold is calibration, and
    the reserved half is measured once with whatever the calibration half chose.
    """
    from .calibrate import CALIBRATION, HeldOutViolation, false_positive_rate
    if corpus.half != CALIBRATION:
        raise HeldOutViolation(
            f"sweep_mass is calibration: choosing a threshold against the {corpus.half} half would "
            f"tune on the material the published figure is measured over")
    from .driver import args_bytes

    detectable = [t for t in transfers if t.detectable_by_design]
    rows = []
    for mass in masses:
        decide = _decider(index, mass)
        fp = false_positive_rate(corpus, redactor, decide=decide,
                                 weighting=f"rarity_mass_{mass}")
        self_hits = sum(
            1 for c in corpus.calls
            if decide(c.target, c.body,
                      frozenset(redactor.kgram_digest_set(args_bytes(c.arguments))), redactor))
        bench_hits = sum(
            1 for t in detectable
            if decide(t.target, t.body,
                      frozenset(redactor.kgram_digest_set(args_bytes(t.arguments))), redactor))
        rows.append({
            "min_rarity_mass": mass,
            "false_positive_rate": fp["rate"],
            "false_positives": fp["false_positives"],
            "self_match_recall": round(self_hits / len(corpus.calls), 4) if corpus.calls else 0.0,
            "bench_recall": round(bench_hits / len(detectable), 4) if detectable else 0.0,
        })
    return rows


def acceptance(shipped_k: int, probe_k: int, *, root: str | Path = ".") -> dict[str, Any]:
    """The whole F1.3 measurement, and the verdict its own numbers imply.

    ``shipped_k`` is where the published comparison is made, because that is the matcher that
    ships. ``probe_k`` is a k at which false positives still exist, because a mechanism cannot be
    shown to work against a rate that is already zero, and reporting only the shipped k would let
    "it did not help" hide "there was nothing left to help with".
    """
    from .calibrate import (
        CALIBRATION,
        HELD_OUT,
        PURPOSE_CALIBRATION,
        PURPOSE_PUBLICATION,
        false_positive_rate,
        load_negative,
        load_positive,
        self_match_recall,
    )

    held = load_negative(HELD_OUT, purpose=PURPOSE_PUBLICATION, root=root)
    cal = load_negative(CALIBRATION, purpose=PURPOSE_CALIBRATION, root=root)
    transfers = load_positive(root=root)

    r_ship = Redactor(k=shipped_k)
    idx_ship = RarityIndex.build(r_ship, root=root)
    un_ship = false_positive_rate(held, r_ship)
    we_ship = false_positive_rate(held, r_ship, decide=_decider(idx_ship, MIN_RARITY_MASS),
                                  weighting=f"rarity_mass_{MIN_RARITY_MASS}")

    r_probe = Redactor(k=probe_k)
    idx_probe = RarityIndex.build(r_probe, root=root)
    un_probe_held = false_positive_rate(held, r_probe)
    we_probe_held = false_positive_rate(held, r_probe,
                                        decide=_decider(idx_probe, MIN_RARITY_MASS),
                                        weighting=f"rarity_mass_{MIN_RARITY_MASS}")
    un_probe_cal = false_positive_rate(cal, r_probe)
    we_probe_cal = false_positive_rate(cal, r_probe, decide=_decider(idx_probe, MIN_RARITY_MASS),
                                       weighting=f"rarity_mass_{MIN_RARITY_MASS}")

    ladder = sweep_mass(cal, transfers, r_probe, idx_probe)
    # The cheapest threshold that removes every false positive at the probe k, and what it costs.
    clean = [row for row in ladder if row["false_positive_rate"] == 0.0]
    cheapest = min(clean, key=lambda row: row["min_rarity_mass"]) if clean else None
    shipped_self = self_match_recall(cal, r_ship)["recall"]

    verdict = (VERDICT_KEPT if we_ship["rate"] < un_ship["rate"] else VERDICT_REVERTED)
    return {
        "name": "rarity_weighting_acceptance",
        "verdict": verdict,
        "criterion": ("the F1.1 rate is re-measured with weighting on and must FALL. If it does "
                      "not, the weighting is reverted and why is documented; it is not kept for "
                      "being more sophisticated"),
        "published_comparison": {
            "half": HELD_OUT, "k": shipped_k, "min_rarity_mass": MIN_RARITY_MASS,
            "unweighted_rate": un_ship["rate"], "weighted_rate": we_ship["rate"],
            "unweighted_false_positives": un_ship["false_positives"],
            "weighted_false_positives": we_ship["false_positives"],
            "pairs": un_ship["pairs"],
            "fell": we_ship["rate"] < un_ship["rate"],
        },
        "mechanism_probe": {
            "k": probe_k,
            "why": ("at the shipped k the unweighted rate is already zero on this corpus, so no "
                    "mechanism can lower it. This k is where false positives still exist, which is "
                    "the only place the mechanism itself can be observed working or failing"),
            "held_out": {"unweighted_rate": un_probe_held["rate"],
                         "weighted_rate": we_probe_held["rate"]},
            "calibration": {"unweighted_rate": un_probe_cal["rate"],
                            "weighted_rate": we_probe_cal["rate"]},
            "colliding_kgrams": colliding_kgram_frequencies(cal, r_probe, idx_probe),
            "true_match_kgrams": true_match_kgram_counts(transfers, r_probe),
            "mass_ladder": ladder,
        },
        "what_a_working_threshold_would_be_doing": {
            "cheapest_mass_that_clears_all_false_positives": (
                cheapest["min_rarity_mass"] if cheapest else None),
            "self_match_recall_there": cheapest["self_match_recall"] if cheapest else None,
            "self_match_recall_at_the_shipped_k_without_weighting": shipped_self,
            "note": ("compare the last two. If the k the sweep chose reaches the same zero with "
                     "HIGHER recall on realistic material, then the threshold is buying nothing "
                     "that the k choice has not already bought, and what it is thresholding is "
                     "match length rather than rarity"),
        },
        "background": idx_ship.citation(),
        "command": "make rarity",
    }
