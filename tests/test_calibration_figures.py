"""The calibration figures are committed, and the prose that quotes them cannot drift from them.

Same arrangement as the run aggregates under docs/figures/ (tests/test_committed_figures.py), for
the same reason: gate rule 6 wants a command behind every published figure, and a figure quoted in a
document is only re-derivable if the artifact it came from is in the repository. The difference is
that these are fully re-derivable by anyone, because the corpus they are measured over IS committed:
`make fp` reproduces the file byte for byte on any machine, with no Docker and no network.

So these tests check three things: the artifact says what it was measured at, the prose quotes it
verbatim, and the reserved half is not being published in a form that could be confused with the
calibration half.
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CALIB_FIGURES = REPO / "docs" / "figures" / "calibration"
DOC = REPO / "docs" / "CALIBRATION.md"


def _artifacts() -> list[Path]:
    return sorted(CALIB_FIGURES.glob("fp-*.json"))


def test_a_published_false_positive_figure_is_committed():
    """Gate rule 9 turns on this number, so it has to be re-derivable from the repository."""
    published = [p for p in _artifacts() if "held-out" in p.name]
    assert published, "no held-out false-positive figure committed; run `make fp`"


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_figure_carries_the_parameters_that_make_it_comparable(path):
    """A rate quoted without k and without the weighting state is not a rate, it is a rumour."""
    d = json.loads(path.read_text())
    assert d["k"] >= 1
    assert d["half"] in ("calibration", "held_out")
    assert d["pairs"] >= 200, "the acceptance criterion was at least 200 pairs"
    assert d["command"].startswith("make fp")
    assert d["name"] == "matcher_false_positive_rate_on_structured_language"
    # The filename has to agree with the contents, or two incomparable figures can overwrite
    # each other's conclusions while both look current.
    assert f"k{d['k']}" in path.name
    assert d["half"].replace("_", "-") in path.name
    assert ("weighted" if d.get("rarity_weighting") else "unweighted") in path.name


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_figure_is_byte_stable(path):
    d = json.loads(path.read_text())
    assert path.read_text() == json.dumps(d, indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_pooled_figure_is_the_sum_of_its_families(path):
    d = json.loads(path.read_text())
    assert d["pairs"] == sum(f["pairs"] for f in d["by_family"].values())
    assert d["false_positives"] == sum(f["false_positives"] for f in d["by_family"].values())
    lo, hi = d["wilson_95"]
    assert lo <= d["rate"] <= hi


def _published() -> dict:
    return json.loads((CALIB_FIGURES / "fp-held-out-k16-unweighted.json").read_text())


def test_the_document_quotes_the_artifact_and_not_a_remembered_number():
    """Every figure in the F1.1 section is rebuilt from the artifact and required verbatim.

    Rebuilt rather than spot-checked: the first version of the equivalent test for threat 10 only
    asserted that one number appeared somewhere in the section, so softening a different occurrence
    of it passed. Here the pooled sentence and every family row are reconstructed from the file.
    """
    d = _published()
    text = " ".join(DOC.read_text().split())

    headline = (f"**Held-out half, k = {d['k']}, no weighting: {d['false_positives']} false "
                f"positives in {d['pairs']} pairs, a rate of {d['rate']}, Wilson 95% interval "
                f"[{d['wilson_95'][0]}, {d['wilson_95'][1]}].**")
    assert headline in text, f"the document does not state the measured result: {headline!r}"

    for family, f in d["by_family"].items():
        row = (f"| `{family}` | {f['pairs']} | {f['false_positives']} | {f['rate']} | "
               f"[{f['wilson_95'][0]}, {f['wilson_95'][1]}] |")
        assert row in text, f"row for {family} does not match the artifact: {row!r}"


def test_the_document_states_the_pair_count_the_acceptance_criterion_asked_for():
    text = " ".join(DOC.read_text().split())
    assert f"**{_published()['pairs']} ordered pairs per half**" in text


def test_the_document_names_the_command_and_the_artifact():
    text = DOC.read_text()
    assert "make fp" in text and "fp-held-out-k16-unweighted.json" in text


def test_the_document_carries_its_own_threats():
    """A measurement that does not say how it could be wrong is not a measurement (gate rule 6)."""
    text = DOC.read_text()
    section = text.split("## Threats to this measurement")[1]
    numbered = re.findall(r"^\d+\. \*\*", section, flags=re.MULTILINE)
    assert len(numbered) >= 4, f"only {len(numbered)} threats stated"
    assert "hand-authored" in section
    assert "model of a server" in section


def test_the_document_keeps_the_two_pending_pieces_marked_pending():
    """F1.2 and F1.3 are unmeasured until they are measured; a doc that reads finished invites a quote."""
    text = DOC.read_text()
    for heading in ("## F1.2", "## F1.3"):
        block = text.split(heading)[1].split("\n## ")[0]
        if "Pending" not in block:
            # Once a piece lands, its section must carry a measured figure and its command instead.
            assert "make " in block, f"{heading} is neither pending nor backed by a command"


def test_no_calibration_figure_leaks_corpus_content():
    """The figures are counts. A false positive is interesting; the string that caused it is data.

    The negative corpus is synthetic and committed, so nothing here is sensitive, but the habit is
    the point: an artifact that quoted the colliding fragment would be the one place in this
    repository where published output carries payload bytes.
    """
    import json as _json
    for path in _artifacts():
        text = path.read_text()
        for half_file in ("calibration.json", "held-out.json"):
            data = _json.loads((REPO / "corpus" / "negative" / half_file).read_text())
            for fam in data["families"]:
                for call in fam["calls"]:
                    for item in call["information"]:
                        assert item not in text, f"{path.name} quotes corpus content: {item!r}"


# --- F1.2: the curve, the choice, and the prose that quotes both.

def _curve() -> dict:
    return json.loads((CALIB_FIGURES / "ksweep-calibration.json").read_text())


def test_the_committed_curve_covers_the_whole_swept_range_every_integer():
    """A coarse step can step straight over a knee, and the knee is the result."""
    from mcpfanout.calibrate import K_MAX, K_MIN
    curve = _curve()
    ks = [r["k"] for r in curve["curve"]]
    assert ks == list(range(K_MIN, K_MAX + 1)), (ks[0], ks[-1], len(ks))
    assert curve["half"] == "calibration"
    assert curve["command"] == "make ksweep"


def test_every_row_of_the_curve_carries_all_three_quantities():
    """Any one of them alone picks a different k, so a row missing one is unusable."""
    for row in _curve()["curve"]:
        assert set(row["false_positives"]) >= {"rate", "count", "pairs", "wilson_95"}
        assert "recall" in row["self_match"]
        assert {"recall", "known_negatives_detected"} <= set(row["bench"])


def test_the_curve_never_detects_a_known_negative_at_any_k():
    """A k that "detects" a header or a gzipped body is counting a collision as a success."""
    offenders = [(r["k"], r["bench"]["known_negatives_detected_by_reason"])
                 for r in _curve()["curve"] if r["bench"]["known_negatives_detected"]]
    assert not offenders, offenders


def test_the_document_quotes_the_curve_rows_verbatim():
    """The F1.2 table is rebuilt from the artifact, the same way the F1.1 figures are."""
    rows = {r["k"]: r for r in _curve()["curve"]}
    text = " ".join(DOC.read_text().split())
    quoted = re.findall(r"\| (\d+) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \|", text)
    assert len(quoted) >= 8, f"the k table has {len(quoted)} rows; the document lost its curve"
    for k, fp, bench, self_match in quoted:
        row = rows[int(k)]
        assert float(fp) == row["false_positives"]["rate"], (k, fp)
        assert float(bench) == row["bench"]["recall"], (k, bench)
        assert float(self_match) == row["self_match"]["recall"], (k, self_match)


def test_the_document_quotes_the_holdout_confirmation_at_the_chosen_k():
    """The point of reserving a half is that the choice is confirmed somewhere it was not tuned."""
    from mcpfanout.shingle import DEFAULT_K
    chosen = _curve()["choice"]["chosen_k"]
    assert chosen == DEFAULT_K
    d = json.loads((CALIB_FIGURES / f"fp-held-out-k{chosen}-unweighted.json").read_text())
    text = " ".join(DOC.read_text().split())
    assert (f"**{d['false_positives']} false positives in {d['pairs']} pairs, a rate of "
            f"{d['rate']}, Wilson 95% [{d['wilson_95'][0]}, {d['wilson_95'][1]}]**") in text
    assert f"It picks k = {chosen}.**" in text


def test_the_document_prices_the_cost_of_the_larger_k():
    """A sweep that reports only what it gained is an argument, not a measurement."""
    # Whitespace collapsed: the prose is hard-wrapped, so a claim can be split across a line break
    # without changing. Matching raw text would fail on reflowing, which is failing for the wrong
    # reason (the same fix threat 10's test needed).
    text = " ".join(DOC.read_text().split())
    section = text.split("## F1.2")[1].split("## F1.3")[0]
    assert "What it cost" in section
    assert "false negative" in section
    # And the claim that the bench column must be read last, because its cliff is an artefact of
    # the bench's own fragment length rather than evidence about real material.
    assert "by design" in section or "BY DESIGN" in section


# --- The self-match ceiling, and the rule that number 5 cannot be published without it.

def _inventory() -> dict:
    from mcpfanout.shingle import DEFAULT_K
    return json.loads((CALIB_FIGURES / f"inventory-k{DEFAULT_K}.json").read_text())


def test_the_inventory_measures_both_floors_and_says_they_differ():
    """Exact-k-gram matching and the winnowing guarantee are different promises.

    Conflating them would overstate what is safe: between k and w + k - 1 a match enters the numbers
    but is not guaranteed to be present in the winnowed fingerprints that get persisted, so a later
    audit of the stored digests may not reconstruct it.
    """
    from mcpfanout.shingle import DEFAULT_K, DEFAULT_W
    inv = _inventory()
    assert inv["floor_exact_kgram_match"] == DEFAULT_K
    assert inv["floor_winnowing_guarantee"] == DEFAULT_K + DEFAULT_W - 1
    assert inv["floor_winnowing_guarantee"] > inv["floor_exact_kgram_match"]


def test_the_inventory_defines_self_match_before_reporting_it():
    """A number this load-bearing cannot travel without its definition attached."""
    inv = _inventory()
    definition = inv["what_self_match_is"]
    assert "args_bytes" in definition
    assert "its own cause" in definition or "is its own cause" in definition
    assert "never be attributed by content anywhere" in definition
    assert inv["measured_over"].endswith("calibration.json"), inv["measured_over"]


def test_the_inventory_covers_all_three_populations():
    """Planted bait, realistic arguments, and the bench as contrast are not interchangeable."""
    inv = _inventory()
    assert inv["planted_bait_by_bucket"], "no bait measured"
    assert inv["realistic_arguments"]["by_family"], "no realistic material measured"
    assert inv["phase_a_transfers_for_contrast"]["transfers"] > 0


def test_the_planted_bait_is_above_both_floors():
    """If the bait were marginal, the ceiling would be partly our own doing and fixable.

    It is not: the k + 8 rule in tests/test_corpus_matches_probes.py keeps every planted value above
    the winnowing floor, which is what lets the ceiling be attributed to ordinary argument material.
    """
    buckets = _inventory()["planted_bait_by_bucket"]
    assert buckets.get("below_k_invisible", 0) == 0, buckets
    assert buckets.get("matched_but_below_winnowing_floor", 0) == 0, buckets


def test_the_document_quotes_the_inventory_per_family():
    """The decomposition is the point: "0.5" alone reads as a defect rather than as a limit."""
    inv = _inventory()
    text = " ".join(DOC.read_text().split())
    for family, f in inv["realistic_arguments"]["by_family"].items():
        lcr = f["longest_common_run"]
        row = (f"| `{family}` | {f['calls']} | {f['self_match_recall']} | "
               f"{lcr['min']} / {lcr['median']} / {lcr['max']} |")
        assert row in text, f"the document's row for {family} does not match the artifact: {row!r}"
    assert f"it was already the level at k = 16" in text


def test_number_5_carries_the_lower_bound_caveat_in_its_own_output():
    """The caveat has to travel WITH the figure. A sentence in a document is not attached to a JSON.

    This is the mechanical form of "number 5 may not be published without that sentence": the field
    is in the aggregate, so it is in every committed artifact and in every printed run of make n5.
    """
    from mcpfanout.aggregate import Run, number_5
    from mcpfanout.record import RunManifest
    run = Run(RunManifest(run_id="r", created="1970-01-01T00:00:00Z", salt_fixed=True, k=22, w=8,
                          corpus_sha256="0" * 64), [], [])
    out = number_5(run)
    assert out["published_as"] == "lower_bound"
    reason = out["published_as_reason"]
    assert "self-match" in reason and "floor and not an estimate" in reason
    assert "make inventory" in reason


def test_every_document_that_publishes_number_5_states_the_lower_bound():
    """Three documents quote number 5. All three have to carry the reason, or one of them is a trap."""
    for name, marker in (("CALIBRATION.md", "published as a LOWER BOUND"),
                         ("THREATS.md", "published as a LOWER BOUND"),
                         ("THE-SIX-NUMBERS.md", "Published as a lower bound")):
        text = " ".join((REPO / "docs" / name).read_text().split())
        assert marker in text, f"docs/{name} does not state that number 5 is a lower bound"
        assert "self-match" in text, f"docs/{name} states the bound without its reason"


def test_the_committed_aggregates_carry_the_caveat_too():
    """An artifact published before the caveat existed would be quotable without it."""
    figures = sorted(p for p in (REPO / "docs" / "figures").glob("*.json")
                     if not p.name.endswith("-instrument.json"))
    stale = []
    for path in figures:
        n5 = {n["number"]: n for n in json.loads(path.read_text())["numbers"]}[5]
        if n5.get("published_as") != "lower_bound":
            stale.append(path.name)
    assert not stale, (f"these committed aggregates predate the lower-bound caveat and must be "
                       f"regenerated with `make figures RUN=...`: {stale}")
