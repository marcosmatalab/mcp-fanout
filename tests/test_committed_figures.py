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
    return sorted(FIGURES.glob("*.json"))


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
