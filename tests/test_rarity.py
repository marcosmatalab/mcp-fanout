"""F1.3: the rarity-weighting experiment, its verdict, and the rule that a reverted idea stays off.

The acceptance criterion F1.3 was given is a number: re-measure the false-positive rate with
weighting on, and if it does not fall, revert the weighting and document why rather than keeping it
because it is more sophisticated. So the tests here fall into two groups.

**The mechanism is correct on its own terms.** Document frequency is counted per document and not
per
occurrence, an unseen k-gram weighs 1.0, weights fall as frequency rises, a mass threshold of one
unseen k-gram is met by exactly that, and an index built at one k refuses to be used at another. If
any of that were wrong the verdict would be measuring a bug rather than the idea.

**The verdict is enforced, not narrated.** While the committed figure says `reverted`, neither
`match.py` nor the capture addon may import this module: that is what "do not leave it switched on"
means in a repository where anybody can wire something up later and nothing would notice. And the
reserved half may never enter the background corpus, because weighting learned from the half the
figure is measured over would be scoring the matcher against material it had already seen.
"""

import json
from pathlib import Path

import pytest

from mcpfanout import match as _match
from mcpfanout.calibrate import (
    CALIBRATION,
    HELD_OUT,
    PURPOSE_CALIBRATION,
    PURPOSE_PUBLICATION,
    HeldOutViolation,
    load_negative,
    load_positive,
)
from mcpfanout.driver import args_bytes
from mcpfanout.rarity import (
    BACKGROUND_SOURCES,
    VERDICT_KEPT,
    VERDICT_REVERTED,
    BackgroundLeak,
    RarityIndex,
    claims_match_weighted,
    sweep_mass,
)
from mcpfanout.redact import Redactor
from mcpfanout.shingle import DEFAULT_K

REPO = Path(__file__).resolve().parent.parent
FIGURE = REPO / "docs" / "figures" / "calibration" / f"rarity-acceptance-k{DEFAULT_K}.json"


def _index(k: int = DEFAULT_K) -> RarityIndex:
    return RarityIndex.build(Redactor(k=k), root=REPO)


# --- The mechanism.

def test_an_unseen_kgram_weighs_one_and_a_frequent_one_weighs_less():
    idx = _index()
    assert idx.weight("f" * 32) == 1.0, "a digest absent from the background must carry full weight"
    frequent = max(idx.df.items(), key=lambda kv: kv[1])
    assert idx.weight(frequent[0]) < 1.0
    assert idx.weight(frequent[0]) == 1.0 / (1.0 + frequent[1])


def test_frequency_is_counted_per_document_not_per_occurrence():
    """A run repeated four hundred times inside one file is one document's worth of evidence.

    Built over a two-file background where one file repeats a phrase many times: if occurrences were
    counted, its frequency would be in the hundreds and its weight would collapse.
    """
    root = Path(pytest.importorskip("tempfile").mkdtemp())
    (root / "corpus" / "background").mkdir(parents=True)
    (root / "a.txt").write_text("the same long phrase here " * 50)
    (root / "b.txt").write_text("something else entirely different in here")
    (root / "corpus" / "background" / "sources.json").write_text(
        json.dumps({"documents": ["a.txt", "b.txt"]}))
    idx = RarityIndex.build(Redactor(k=16), root=root)
    assert idx.documents == 2
    assert max(idx.df.values()) <= 2, "document frequency cannot exceed the number of documents"


def test_the_threshold_means_one_kgram_the_background_has_never_seen():
    """The default is expressed in that unit, so it has to behave like it."""
    idx = _index()
    r = Redactor()
    novel = b"absolutely-unseen-material-" + b"zq7x" * 8
    digests = frozenset(r.kgram_digest_set(novel))
    assert claims_match_weighted(novel, b"", digests, r, idx, min_mass=1.0)
    # A mass threshold above the total mass of everything that matched cannot be met.
    huge = float(len(digests) + 1)
    assert not claims_match_weighted(novel, b"", digests, r, idx, min_mass=huge)


def test_nothing_matched_is_never_a_match_whatever_the_threshold():
    idx = _index()
    r = Redactor()
    assert not claims_match_weighted(b"/nothing/in/common", b"", frozenset(), r, idx, min_mass=0.0)


def test_an_index_built_at_another_k_is_refused():
    """A weight looked up at the wrong k is a weight for a different byte sequence."""
    idx = _index(k=16)
    r = Redactor(k=22)
    with pytest.raises(ValueError, match="different byte sequence"):
        claims_match_weighted(b"abc", b"", frozenset(), r, idx)


def test_the_weighted_decision_reuses_the_shipped_matchers_own_kgram_set():
    """Two implementations of "which k-grams matched" would let the figure describe another matcher.

    """
    r = Redactor()
    call = load_negative(CALIBRATION, purpose=PURPOSE_CALIBRATION, root=REPO).calls[0]
    digests = frozenset(r.kgram_digest_set(args_bytes(call.arguments)))
    matched = (_match.argument_kgrams_present(call.target, digests, r)
               | _match.argument_kgrams_present(call.body, digests, r))
    # The shipped matcher's boolean and the helper's set have to agree about emptiness.
    shipped = _match.match_request(call.target, call.body, {}, digests, r).causal
    assert shipped == bool(matched)


# --- The guards.

def test_the_reserved_half_may_never_be_a_background_document():
    root = Path(pytest.importorskip("tempfile").mkdtemp())
    (root / "corpus" / "background").mkdir(parents=True)
    (root / "corpus" / "negative").mkdir(parents=True)
    (root / "corpus" / "negative" / "held-out.json").write_text("{}")
    (root / "corpus" / "background" / "sources.json").write_text(
        json.dumps({"documents": ["corpus/negative/*.json"]}))
    with pytest.raises(BackgroundLeak):
        RarityIndex.build(Redactor(), root=root)


def test_the_declared_background_excludes_the_reserved_half_and_says_why():
    spec = json.loads((REPO / BACKGROUND_SOURCES).read_text())
    assert "held-out.json" in json.dumps(spec["excluded"]) or "held-out" in spec["_never"]
    for pattern in spec["documents"]:
        assert "held-out" not in pattern
    # And the built index must not contain it either, which the loader enforces independently.
    assert all("held-out" not in s for s in _index().sources)


def test_the_threshold_sweep_refuses_the_reserved_half():
    """Choosing a threshold is calibration, wherever the corpus object came from."""
    held = load_negative(HELD_OUT, purpose=PURPOSE_PUBLICATION, root=REPO)
    with pytest.raises(HeldOutViolation):
        sweep_mass(held, load_positive(root=REPO), Redactor(), _index(), masses=(1.0,))


# --- The verdict, and what it obliges.

def test_the_verdict_is_committed_with_the_numbers_that_produced_it():
    d = json.loads(FIGURE.read_text())
    assert d["verdict"] in (VERDICT_KEPT, VERDICT_REVERTED)
    pc = d["published_comparison"]
    assert pc["half"] == HELD_OUT, "the verdict must come from the reserved half"
    assert pc["k"] == DEFAULT_K, "and from the k that actually ships"
    assert pc["pairs"] >= 200
    # The verdict follows from the numbers rather than sitting beside them.
    assert (d["verdict"] == VERDICT_KEPT) == (pc["weighted_rate"] < pc["unweighted_rate"])
    assert pc["fell"] == (pc["weighted_rate"] < pc["unweighted_rate"])


def test_a_reverted_weighting_is_not_wired_into_anything():
    """"Reverted" has to mean the matcher does not use it, not that a comment says it should not.

    Checked as an import-level fact over the shipped matching path: match.py, the capture addon, and
    the aggregate. If a future change wires the weighting in, this fails until the verdict in the
    committed figure changes too, which is exactly the order those two things should happen in.
    """
    import re
    if json.loads(FIGURE.read_text())["verdict"] != VERDICT_REVERTED:
        pytest.skip("the verdict is kept; the weighting is allowed in the matching path")
    # Imports and call sites, not the word: match.py's own docstring explains why its k-gram helper
    # is public, and naming the experiment there is documentation rather than wiring. A test that
    # could not tell those apart would force the explanation out of the file that needs it.
    use = re.compile(r"^\s*(?:from|import)\s+\S*rarity|(?<![\w.])rarity\s*\.", re.MULTILINE)
    for name in ("match.py", "capture_addon.py", "aggregate.py", "record.py", "redact.py"):
        text = (REPO / "src" / "mcpfanout" / name).read_text()
        hit = use.search(text)
        assert hit is None, f"{name} wires in the reverted weighting: {hit.group(0)!r}"


def test_the_mechanism_probe_explains_itself_rather_than_only_reporting_a_failure():
    """"It did not help" without a mechanism is a shrug recorded as a result."""
    probe = json.loads(FIGURE.read_text())["mechanism_probe"]
    assert probe["k"] != DEFAULT_K, "the probe must be at a k where false positives still exist"
    assert probe["held_out"]["unweighted_rate"] > 0, "nothing to observe at this k"
    cg = probe["colliding_kgrams"]
    assert cg["colliding_kgram_instances"] > 0
    assert cg["background_documents"] > 0
    # The diagnosis rests on this: the colliding k-grams are not common in the background.
    frequencies = {int(k): v for k, v in cg["instances_by_document_frequency"].items()}
    assert max(frequencies) <= 1, (
        "the diagnosis in docs/CALIBRATION.md says no colliding k-gram is common in the "
        f"background; the figure now shows frequencies up to {max(frequencies)} and the prose "
        "must be rewritten")
    assert probe["mass_ladder"], "no threshold sweep, so the verdict rests on one guessed threshold"


def test_the_threshold_that_works_is_dominated_by_the_chosen_k():
    """The quantitative reason to revert, asserted rather than left in the prose.

    If a threshold ever reaches zero false positives with HIGHER realistic recall than the shipped k
    achieves unweighted, the argument for reverting collapses and this fails.
    """
    d = json.loads(FIGURE.read_text())
    if d["verdict"] != VERDICT_REVERTED:
        pytest.skip("kept")
    thr = d["what_a_working_threshold_would_be_doing"]
    if thr["cheapest_mass_that_clears_all_false_positives"] is None:
        return  # no threshold clears them at all: an even stronger reason to revert
    unweighted_at_k = thr["self_match_recall_at_the_shipped_k_without_weighting"]
    assert thr["self_match_recall_there"] <= unweighted_at_k, (
        "a threshold now beats the chosen k on recall at the same false-positive rate; the revert "
        "decision in docs/CALIBRATION.md no longer follows from the numbers")


def test_the_document_quotes_the_verdict_figure():
    d = json.loads(FIGURE.read_text())
    pc = d["published_comparison"]
    text = " ".join((REPO / "docs" / "CALIBRATION.md").read_text().split())
    assert "REVERTED" in text if d["verdict"] == VERDICT_REVERTED else True
    assert (f"unweighted {pc['unweighted_false_positives']} of {pc['pairs']}, weighted "
            f"{pc['weighted_false_positives']} of {pc['pairs']}") in text
    thr = d["what_a_working_threshold_would_be_doing"]
    assert str(thr["cheapest_mass_that_clears_all_false_positives"]) in text
    assert str(thr["self_match_recall_there"]) in text
