"""The NEW reserved half, and why it exists.

corpus/negative/held-out.json stopped being a reserve on 2026-09-19. An external review's scripts
loaded it with a bare `json.load`, bypassing `calibrate.load_negative`, and measured it. Its
false-positive figure is a CALIBRATION figure from that moment on, and docs/PREREG-F2.md says so.
This file guards its replacement, `corpus/negative/reserved.json`, under the same invariants the
other two halves are held to, plus one the others do not have: the reserve is GENERATED, so it can
be re-derived and a hand edit to it fails here.

The guard on the loader is a courtesy and this file does not pretend otherwise (see
docs/PREREG-F2.md section 1). What a test CAN do is make a bypass visible afterwards, which is
what `test_no_published_figure_cites_the_reserve_yet` does.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
NEG = REPO / "corpus" / "negative"
RESERVED = NEG / "reserved.json"


def _raw() -> dict:
    return json.loads(RESERVED.read_text(encoding="utf-8"))


def _call_blob(call: dict) -> str:
    return json.dumps(call["arguments"], sort_keys=True) + "\x00" + \
        call["request"]["target"] + "\x00" + call["request"]["body"]


def test_the_reserve_is_re_derivable_from_its_generator():
    """A corpus edited by hand is a corpus whose provenance is a memory. Rule 6, applied to data."""
    r = subprocess.run([sys.executable, "tools/build_negative_extras.py", "--check"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, f"the corpus is out of sync with its generator:\n{r.stdout}{r.stderr}"


def test_it_declares_itself_the_reserved_half():
    assert _raw()["half"] == "reserved"


def test_it_says_in_writing_that_the_loader_guard_is_a_courtesy():
    """Because the previous reserve was lost to exactly the assumption that it was a lock."""
    text = _raw()["_the_guard_is_a_courtesy"]
    assert "courtesy" in text.lower() and "json.load" in text
    assert len(text) > 150


def test_it_shares_no_information_with_either_older_half():
    """A reserve that shares material with a measured half is not a reserve."""
    others = "".join((NEG / f).read_text(encoding="utf-8")
                     for f in ("calibration.json", "held-out.json"))
    offenders = [(c["id"], item)
                 for fam in _raw()["families"] for c in fam["calls"]
                 for item in c["information"] if item in others]
    assert not offenders, f"reserved information also present elsewhere: {offenders[:5]}"


def test_no_call_id_collides_with_an_older_half():
    mine = {c["id"] for fam in _raw()["families"] for c in fam["calls"]}
    for f in ("calibration.json", "held-out.json"):
        theirs = {c["id"] for fam in json.loads((NEG / f).read_text())["families"]
                  for c in fam["calls"]}
        assert not (mine & theirs), f"{f}: id collision {mine & theirs}"


def test_no_two_calls_in_a_family_share_information():
    offenders = []
    for fam in _raw()["families"]:
        for a in fam["calls"]:
            for b in fam["calls"]:
                if a["id"] == b["id"]:
                    continue
                blob = _call_blob(b)
                offenders += [(a["id"], b["id"], i) for i in a["information"] if i in blob]
    assert not offenders, f"shared information: {offenders[:5]}"


def test_every_declared_shared_literal_is_really_shared():
    for fam in _raw()["families"]:
        assert fam["shared_literals"], fam["family"]
        for literal in fam["shared_literals"]:
            for call in fam["calls"]:
                assert literal in _call_blob(call), \
                    f"{fam['family']}/{call['id']} lacks {literal!r}"


def test_a_call_with_no_information_says_why_in_an_argument():
    for fam in _raw()["families"]:
        for call in fam["calls"]:
            if call["information"]:
                continue
            assert len(call.get("information_free", "").strip()) > 120, \
                f"{call['id']}: silent emptiness"


def test_the_corpus_plants_nothing():
    text = RESERVED.read_text(encoding="utf-8")
    assert "CANARY_" not in text
    for real in ("api.github.com", "registry.npmjs.org", "modelcontextprotocol"):
        assert real not in text


def test_it_carries_the_family_built_against_structural_containment():
    """The reserve is worthless against the new matcher without the family that attacks it."""
    fams = {f["family"] for f in _raw()["families"]}
    assert "containment_subset" in fams
    fam = next(f for f in _raw()["families"] if f["family"] == "containment_subset")
    cases = {c["case"] for c in fam["calls"]}
    assert {"subset", "enum", "shared_org", "anchor"} <= cases, cases


def test_enough_pairs_to_carry_a_rate():
    for fam in _raw()["families"]:
        n = len(fam["calls"])
        assert n * (n - 1) >= 42, f"{fam['family']}: {n} calls is too few to state a rate"


@pytest.mark.parametrize("doc", ["docs/PREREG-F2.md", "docs/CALIBRATION.md"])
def test_no_published_figure_cites_the_reserve_yet(doc):
    """The reserve is measured ONCE, at the end. Until then no document may quote a rate from it.

    This cannot stop a bypass, because nothing in a repository can. What it can do is make a
    published figure that came from here fail the suite, which is the difference between a
    courtesy and a courtesy somebody notices.
    """
    text = (REPO / doc).read_text(encoding="utf-8")
    for banned in ("reserved half: 0.0", "reserved half: 0,", "on the reserved half was"):
        assert banned not in text, f"{doc} appears to quote a reserved-half rate: {banned!r}"
