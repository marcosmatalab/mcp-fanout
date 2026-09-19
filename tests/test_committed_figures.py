"""The committed normalized aggregates under docs/figures/ must be clean and must match the docs.

Gate rule 6 wants a command behind every published figure; gate rule 4 refuses to track runs. A
figure quoted in a document was therefore measured but not re-derivable from the repository, a
tension recorded in docs/THREATS.md, threat 10. It is resolved by committing the AGGREGATE rather
than the run, and these tests are what make that safe: an aggregate is only publishable if it
names nothing (rule 3), and it is only useful if the prose that quotes it cannot drift from it.
"""

import json
import re
from pathlib import Path

import pytest

from mcpfanout.classify import PACKAGE_INFRASTRUCTURE_PATH, ExclusionList

REPO = Path(__file__).resolve().parent.parent
FIGURES = REPO / "docs" / "figures"


def _artifacts() -> list[Path]:
    """The six-number normalized aggregates. Instrument artifacts are a different shape."""
    return sorted(p for p in FIGURES.glob("*.json") if not p.name.endswith("-instrument.json"))


def _instrument_artifacts() -> list[Path]:
    """The phase A instrument blocks: recall, precision, false provenance.

    A separate family on purpose. They answer a different question from the six numbers and are
    computable only on a bench run, so keeping them in one file would make it possible to quote a
    recall figure alongside a phenomenon figure as though both described the same thing.
    """
    return sorted(FIGURES.glob("*-instrument.json"))


# Runs driven BEFORE the two-pass split existed (docs/PHASES.md, phase B). Their manifests carry no
# pass, so their artifacts say "unlabelled", which is the honest value: the driving condition was not
# recorded and deriving it from the notes afterwards would be a guess dressed as provenance. Named
# here explicitly so a NEW artifact cannot be unlabelled -- the list does not grow.
LEGACY_UNLABELLED_RUNS = frozenset({"20260918T200935Z", "20260918T212417Z"})


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_artifact_declares_which_pass_produced_it(path):
    """A grade distribution whose driving condition is unknown cannot be read at all.

    The two phase B passes are two experimental conditions, and the label is what stops one being
    quoted as the other. It lives in provenance rather than in the numbers because it describes how
    the run was driven, not what was found.
    """
    doc = json.loads(path.read_text())
    label = doc["provenance"].get("pass")
    assert label, f"{path.name}: no pass label in provenance"
    if label == "unlabelled":
        assert doc["provenance"]["run_id"] in LEGACY_UNLABELLED_RUNS, (
            f"{path.name}: a new artifact may not be unlabelled; drive it with --pass")
    else:
        assert label in ("sequential", "concurrent", "bench", "selftest"), label


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_artifact_carries_the_driving_summary(path):
    """The six are ratios over what servers did in response to calls; this is the denominator.

    Without it a reader cannot tell a server that egresses nothing from a server whose calls all
    errored, and those are opposite findings that produce the same zeros.
    """
    doc = json.loads(path.read_text())
    driving = doc["driving"]
    assert driving["calls_total"] > 0
    assert "by_wave_size" in driving
    assert driving["name"] == "driving_summary"
    # It must not be mistakable for a seventh number.
    assert "not_one_of_the_six" in driving


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_number_5_publishes_the_per_window_breakdown(path):
    """A pooled grade figure cannot show how discrimination behaves as concurrency grows.

    "Strong attribution was 30%" is unreadable without the N it was measured at, and the shape of
    the decay across N is the phase B result that the pre-registered prediction is about
    (docs/PHASES.md, prediction B1).
    """
    n5 = _numbers_of(path)[5]
    assert "grades_by_window_size" in n5
    assert n5["grades_by_window_size"], "the breakdown is empty"
    assert "pass" in n5


def test_at_least_one_normalized_aggregate_is_committed():
    """Without one, threat 10's tension is documented as resolved while still being open."""
    assert _artifacts(), "docs/figures/ is empty; run `make figures` after a capture"


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_artifact_is_a_normalized_aggregate_with_its_command(path):
    d = json.loads(path.read_text())
    assert d["normalized"] is True
    assert d["provenance"]["run_id"] == path.stem, "filename and run id must agree"
    # Rule 2: the command that regenerates the file lives in the file, not only in a Makefile.
    assert "mcpfanout.cli figures" in d["provenance"]["command"]
    assert d["numbers"] and len(d["numbers"]) == 6


def _strings(node, keys=False):
    """Every string in a JSON tree. With keys=True, the object keys too."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            if keys:
                yield k
            yield from _strings(v, keys)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, keys)


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_artifact_names_nothing(path):
    """Gate rule 3, applied to a file that is actually published rather than merely printed.

    Checked against the real server ids and launch commands in the registry and the real host
    suffixes in the exclusion list, not against a hand-written denylist, which would pass by
    omission.

    Server ids are matched as WHOLE strings, not substrings, and that is not a loosening: one of
    the ten servers is called `time`, and a substring check flagged the generated reason string
    "time window and pid only, with 1 call(s) active". The risk rule 3 guards against is a server
    being NAMED as data, in a key or a value; a common English word inside a sentence our own
    code composed from a fixed vocabulary is not that. Host suffixes stay substring-matched,
    because a hostname is distinctive enough that a match is never coincidence.
    """
    import yaml
    doc = json.loads(path.read_text())
    numbers = doc["numbers"]
    registry = yaml.safe_load((REPO / "registry" / "servers.yaml").read_text())

    tokens = set(_strings(numbers, keys=True))
    for server in registry["servers"]:
        assert server["id"] not in tokens, f"{server['id']} appears as a name in the numbers"
        for arg in server["launch"]:
            assert arg not in tokens, f"{arg} appears as a name in the numbers"

    # The provenance block may record which subset was driven, which is a server id by nature.
    # It is provenance about the run, not a figure, and it is the only place ids are allowed.
    numbers_text = json.dumps(numbers)
    exclusions = ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH)
    for suffix in exclusions.suffixes:
        assert suffix not in path.read_text(), f"{suffix} leaked into a committed figure"

    # No payload digests. The run holds those; the aggregate must not. The single exemption is
    # the exclusion list's OWN sha256, which rule 2 requires so the list that produced a figure
    # can be identified, and which is a digest of a committed file rather than of any payload.
    allowed = {exclusions.sha256}
    for candidate in re.findall(r"\b[0-9a-f]{32,}\b", numbers_text):
        assert candidate in allowed, f"an unexplained digest is published: {candidate[:12]}..."


@pytest.mark.parametrize("path", _artifacts(), ids=lambda p: p.name)
def test_the_artifact_is_byte_stable(path):
    """It is committed and diffed, so regenerating it over the same run must not churn."""
    d = json.loads(path.read_text())
    assert path.read_text() == json.dumps(d, indent=2, sort_keys=True) + "\n"


def _numbers_of(path: Path) -> dict:
    return {n["number"]: n for n in json.loads(path.read_text())["numbers"]}


def test_threat_10_quotes_the_committed_artifact_not_a_vanished_run():
    """The figures in threat 10 must be readable out of a file in this repository.

    This is the whole point of committing the aggregate. If the prose and the artifact drift, the
    document is back to quoting a run nobody else can see.
    """
    threats = (REPO / "docs" / "THREATS.md").read_text()
    threat10 = threats.split("10. **A tool call is not atomic")[1].split("\n11.")[0]
    # Collapse whitespace: the prose is hard-wrapped at 100 columns, so a quoted figure can be
    # split across a line break without the claim changing. Matching on raw text would make this
    # test fail on reflowing, which is a rule that fails for the wrong reason.
    threat10 = " ".join(threat10.split())
    run_ids = re.findall(r"`(\d{8}T\d{6}Z)`", threat10)
    assert run_ids, "threat 10 must name the run its figures come from"
    for run_id in set(run_ids):
        artifact = FIGURES / f"{run_id}.json"
        assert artifact.is_file(), (
            f"threat 10 quotes run {run_id} but docs/figures/{run_id}.json is not committed")
        n = _numbers_of(artifact)
        # Every quoted figure is rebuilt FROM the artifact and required to appear verbatim, so
        # drift fails in both directions. The first version of this check only asserted that
        # "87" appeared somewhere in the section, and softening one occurrence to 42 passed
        # because the other occurrences of 87 were still there.
        def dist(d):
            return f"{d['p50']} / {d['p95']} / {d['max']}"

        expected = [
            f"raw {dist(n[1]['connections_raw'])}",
            f"distinct hosts {dist(n[1]['distinct_hosts'])}",
            "excluding package infrastructure "
            f"{dist(n[1]['connections_excluding_package_infrastructure'])}",
            "`package_infrastructure_connections` = "
            f"{n[1]['package_infrastructure_connections']}",
            f"all {n[5]['attribution_grades']['UNATTRIBUTED']} as `UNATTRIBUTED`",
            f"{n[5]['attribution_grades']['TEMPORAL_ONLY']} `TEMPORAL_ONLY`",
            f"{n[5]['attribution_grades']['CONTENT_MATCH_UNCONTESTED']} "
            "`CONTENT_MATCH_UNCONTESTED`",
            f"fraction of {n[5]['strong_attribution_fraction']}",
        ]
        for phrase in expected:
            assert phrase in threat10, (
                f"threat 10 does not quote the artifact: expected {phrase!r}")


# --- Phase A instrument artifacts. Gate rule 8's evidence, and rule 3 still applies to it.

def test_an_instrument_artifact_is_committed():
    """Gate rule 8 blocks phase B on phase A passing, so the pass has to be re-derivable."""
    assert _instrument_artifacts(), (
        "no phase A instrument artifact; gate rule 8 cannot be shown to be satisfied")


@pytest.mark.parametrize("path", _instrument_artifacts(), ids=lambda p: p.name)
def test_the_instrument_artifact_carries_its_command_and_its_author(path):
    d = json.loads(path.read_text())
    assert d["phase"] == "A"
    prov = d["provenance"]
    assert "bench-verify" in prov["command"]
    # Who wrote the ground truth is part of the figure's meaning: a precision number computed
    # against a ledger the sensor could have influenced would be worthless, so the artifact says
    # where the truth came from.
    assert "bench/server.py" in prov["ground_truth_author"]
    assert "imports" in prov["ground_truth_author"]
    for block in ("capture", "attribution", "provenance", "known_negatives", "per_cell"):
        assert block in d["instrument"], block


@pytest.mark.parametrize("path", _instrument_artifacts(), ids=lambda p: p.name)
def test_the_instrument_artifact_publishes_no_destination_host(path):
    """Rule 3 applies to this artifact too, and one field had to be reduced to satisfy it.

    bench_metrics reports hosts_sent_to_but_never_observed as a list of hostnames, which is a
    useful diagnostic for the operator and a rule-3 violation the moment it is committed. The
    artifact carries the count instead; the list stays in the untracked run.
    """
    text = path.read_text()
    assert "bench.invalid" not in text, "a bench destination hostname is published"
    assert "hosts_sent_to_but_never_observed" not in json.loads(text)["instrument"]["capture"]
    assert "hosts_sent_to_but_never_observed_count" in json.loads(text)["instrument"]["capture"]


@pytest.mark.parametrize("path", _instrument_artifacts(), ids=lambda p: p.name)
def test_the_committed_instrument_result_passes_the_sensor_gate(path):
    """The four pre-registered criteria of docs/PHASES.md, read out of the artifact.

    Written as a test rather than left in prose because gate rule 8 turns this on a threshold,
    and a threshold nobody checks is a sentence. If a future bench run regresses, this fails and
    the phase B figures stop being publishable, which is exactly what rule 8 says.
    """
    inst = json.loads(path.read_text())["instrument"]
    assert inst["ok"] is True
    assert inst["capture"]["capture_recall"] >= 0.95, inst["capture"]
    # Tolerance zero, not negotiable: one false strong attribution destroys the evidentiary claim.
    assert inst["attribution"]["false_strong_attributions"] == 0, inst["attribution"]
    assert inst["provenance"]["false_provenance_rate"] < 0.01, inst["provenance"]
    # And the thesis has to have actually been exercised, or the gate passes on an empty bench.
    assert inst["attribution"]["strong_attributions"] > 0, (
        "no strong attribution was produced at all; the bench did not exercise the thesis")


@pytest.mark.parametrize("path", _instrument_artifacts(), ids=lambda p: p.name)
def test_every_discrimination_cell_got_the_grade_it_predicted(path):
    """The cells are pre-registered predictions, so each one is checked against its own claim.

    The mixture cell is checked on the SPLIT rather than on a single grade, because right counts
    with the wrong pairing is a failure and a per-cell grade tally alone cannot see it: the
    comparator's per-flow correct_call and wrong_call are what settle it.
    """
    cells = json.loads(path.read_text())["instrument"]["per_cell"]
    for name, expected in (("all_distinct", "CONTENT_UNIQUE"),
                           ("all_shared", "CONTENT_AMBIGUOUS"),
                           ("no_arguments", "UNATTRIBUTED"),
                           ("target_channel", "CONTENT_UNIQUE"),
                           ("header_channel", "UNATTRIBUTED")):
        cell = cells[name]
        assert set(cell["grades"]) == {expected}, f"{name}: {cell['grades']}"
        assert cell["flows"] > 0, name

    mixture = cells["two_shared_rest_distinct"]
    assert set(mixture["grades"]) == {"CONTENT_UNIQUE", "CONTENT_AMBIGUOUS"}, mixture["grades"]
    assert mixture["wrong_call"] == 0, "the mixture cell attributed a flow to the wrong call"
    assert mixture["correct_call"] == mixture["grades"]["CONTENT_UNIQUE"]
    assert mixture["no_call"] == mixture["grades"]["CONTENT_AMBIGUOUS"]


@pytest.mark.parametrize("path", _instrument_artifacts(), ids=lambda p: p.name)
def test_the_known_negatives_really_were_missed(path):
    """A known negative that the sensor accidentally caught would not be sizing anything.

    These cells exist to produce the figure for what byte-literal matching loses (negative 3).
    If the sensor attributed one strongly, the cell would be measuring a hit while being reported
    as a loss.
    """
    inst = json.loads(path.read_text())["instrument"]
    kn = inst["known_negatives"]
    assert kn["flows_carrying_material_in_an_unread_channel"] > 0, "nothing was measured"
    assert kn["of_which_the_sensor_attributed_strongly"] == 0
    for cell in ("reencoded_base64", "reencoded_gzip", "reencoded_json_escaped"):
        grades = inst["per_cell"][cell]["grades"]
        assert "CONTENT_UNIQUE" not in grades and "CONTENT_AMBIGUOUS" not in grades, (
            f"{cell}: a re-encoded payload produced a content match, so it left a literal run")


@pytest.mark.parametrize("path", _instrument_artifacts(), ids=lambda p: p.name)
def test_late_egress_is_unattributed_rather_than_pinned_to_the_last_call(path):
    """Egress after its wave has no window to sit in, and must not be guessed at.

    This is the case that shows a time window is not a substitute for content: the harness clears
    the in-flight set after each wave precisely so this comes out honest.
    """
    cells = json.loads(path.read_text())["instrument"]["per_cell"]
    assert set(cells["late_egress"]["grades"]) == {"UNATTRIBUTED"}, cells["late_egress"]
    assert cells["late_egress"]["no_call"] == cells["late_egress"]["flows"]
