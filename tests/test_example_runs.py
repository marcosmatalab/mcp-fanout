"""The two committed example runs must still produce the figures this repository published.

Gate 6 (`make reproduce`) as a test. The example runs are redacted copies of the two captures
(runs/README.md), and the whole reason they are in the tree is that a reader can recompute the six
numbers without Docker, without network and without credentials. That promise is worth exactly as
much as a test that fails when it stops being true.

Why it compares against `docs/figures/` rather than against a stored expectation: the figures were
produced from the CAPTURES, which nobody else has. Comparing the redacted run against them is
therefore the only check that can catch a redaction that quietly changed a number, which is the
failure mode that matters here. A redactor that dropped every package-infrastructure flow would
still produce a self-consistent run, and a test written against the redacted run's own output would
pass on it.

The three fields a redacted run adds are listed and allowed by name, not by a wildcard: they are
the record of the classification having been carried, and a test that ignored unknown extra fields
would also ignore a new field that changed a number.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mcpfanout.aggregate import Run, compute_all
from mcpfanout.classify import (
    CONSTANT_PATHS_PATH,
    PACKAGE_INFRASTRUCTURE_PATH,
    ConstantPathList,
    ExclusionList,
)

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "runs"
FIGURES = REPO / "docs" / "figures"

# example run -> the committed aggregate of the capture it was redacted from.
PAIRS = {
    "example-sequential": "20260919T115452Z-sequential.json",
    "example-concurrent": "20260919T194649Z-concurrent.json",
    "example-blind-proxy": "20260919T193121Z-concurrent.json",
}

# Fields a redacted run adds, and nothing else may differ. Each one exists because the run has no
# hostname left to apply a registry list to, and each one is what tells a reader so.
ADDED_BY_REDACTION = {
    "/numbers[0]/exclusion_list/classification",
    "/numbers[0]/exclusion_list/computed_against_sha256",
    "/numbers[0]/exclusion_list/list_digest_still_matches",
    "/numbers[5]/node_categories",
}


# A note whose text cites a repository document is prose about the repository, not a measurement.
# Three governance documents were merged into docs/PROTOCOL.md, so the aggregator's notes name a
# file the figures published before the merge could not name. Document names are therefore
# normalised inside these strings and ONLY inside them, and any other difference in one still
# fails: the point of this file is that the numbers reproduce, and a note is not a number.
DOC_PATH = re.compile(r"docs/[A-Z0-9-]+\.md")


def _normalise_doc_paths(value: str) -> str:
    return DOC_PATH.sub("docs/<a document>", value)


def _differences(redacted, published, path=""):
    """Every point where two aggregates differ, as (kind, path) pairs."""
    out = []
    if (isinstance(redacted, str) and isinstance(published, str)
            and _normalise_doc_paths(redacted) == _normalise_doc_paths(published)):
        return out
    if isinstance(redacted, dict) and isinstance(published, dict):
        for key in sorted(set(redacted) | set(published)):
            here = f"{path}/{key}"
            if key in redacted and key in published:
                out += _differences(redacted[key], published[key], here)
            elif key not in published:
                out.append(("added-by-redaction", here))
            else:
                out.append(("missing-from-redacted", here))
    elif isinstance(redacted, list) and isinstance(published, list):
        if len(redacted) != len(published):
            out.append(("length", f"{path} {len(redacted)} != {len(published)}"))
        else:
            for index, (a, b) in enumerate(zip(redacted, published, strict=True)):
                out += _differences(a, b, f"{path}[{index}]")
    elif redacted != published:
        out.append(("changed", f"{path}: {redacted!r} != {published!r}"))
    return out


def _computed(name: str) -> dict:
    run = Run.load(RUNS / name)
    return compute_all(
        run,
        exclusions=ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH),
        constant_paths=ConstantPathList.load(REPO / CONSTANT_PATHS_PATH),
    )


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_the_example_run_is_committed_and_loadable(name):
    for required in ("manifest.json", "calls.jsonl", "flows.jsonl"):
        assert (RUNS / name / required).is_file(), (
            f"runs/{name}/{required} is missing; `make reproduce` and five Quickstart commands "
            "depend on it. Regenerate with tools/redact_run.py (see runs/README.md)")
    run = Run.load(RUNS / name)
    assert run.calls and run.flows
    assert run.manifest.redaction, (
        f"runs/{name} does not declare itself redacted; a run in the tree that does not say it "
        "was redacted is indistinguishable from a captured one that should never have been "
        "committed")


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_every_published_number_reproduces_from_the_committed_run(name):
    computed = _computed(name)
    published = json.loads((FIGURES / PAIRS[name]).read_text(encoding="utf-8"))
    problems = []
    for kind, where in _differences({"numbers": computed["numbers"]},
                                    {"numbers": published["numbers"]}):
        if kind == "added-by-redaction" and where in ADDED_BY_REDACTION:
            continue
        problems.append(f"{kind}: {where}")
    assert not problems, (
        f"runs/{name} no longer reproduces docs/figures/{PAIRS[name]}:\n  "
        + "\n  ".join(problems))


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_the_run_names_no_server_no_host_and_no_tool(name):
    """The reason runs were never committed. Checked here, not left to a grep in a README.

    Deliberately a denylist of what these ten servers and their destinations are called, not a
    general scan: a general scan for "anything host-shaped" would fail on `third-party-a` and pass
    on a vendor's name it had not been told about, which is the wrong way round.
    """
    forbidden = ("npmjs", "github", "google", "brave", "puppeteer", "modelcontextprotocol",
                 "example.net", "filesystem", "sequential-thinking", "BRAVE_API_KEY",
                 "GITHUB_PERSONAL_ACCESS_TOKEN")
    for path in sorted((RUNS / name).iterdir()):
        if path.suffix == ".pcap" or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        hits = sorted({needle for needle in forbidden if needle.lower() in text})
        assert not hits, f"runs/{name}/{path.name} names {hits}"


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_the_carried_classification_still_matches_the_list_it_was_computed_against(name):
    """A carried answer is only as good as the guarantee that its input has not moved."""
    manifest = json.loads((RUNS / name / "manifest.json").read_text(encoding="utf-8"))
    carried = manifest["redaction"]["package_infrastructure_sha256"]
    current = ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH)
    assert current is not None
    assert carried == current.sha256, (
        "registry/package-infrastructure.json has changed since these runs were redacted, so "
        "their numbers 1 and 5 describe the list as it was. Re-redact from the captures, or "
        "publish the divergence: what is not allowed is leaving the output saying the digests "
        "match when they do not")


def _backstop(run: str) -> dict:
    import subprocess
    import sys
    out = subprocess.run([sys.executable, str(REPO / "tools" / "pcap_syns.py"), "--run", run],
                         cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert all(host.startswith(("192.0.2.", "127.0.0.1")) for host in data["by_destination"]), (
        "the backstop carries an address outside the documentation range")
    return data


def test_the_backstop_survives_redaction_with_its_counts_intact():
    """Threat 19's evidence is a SYN count per destination. A redaction that changed it would
    destroy the one measurement the proxy could not make. It is asserted on the run the finding is
    read from: this test once asserted a count of 10 on example-concurrent, where that 10 is a
    proxied destination that matched the finding's figure by coincidence."""
    data = _backstop("example-blind-proxy")
    assert data["outbound_syns"] == 140, data["outbound_syns"]
    # The ten connections that went straight past the proxy: an address no flow names.
    assert data["unobserved_destinations"].get("192.0.2.201:443") == 10, data
    silent = [row for row in data["servers"].values()
              if row["completed"] == 16 and row["calls"] == 17
              and row["proxy_flows_during_calls"] == 0]
    assert len(silent) == 1, data["servers"]


def test_the_corrected_run_has_no_unobserved_https_destination():
    """The other half of threat 19: with NODE_USE_ENV_PROXY on, the proxy sees the API. What is
    left unobserved is plain HTTP on port 80, not the connections the finding is about."""
    data = _backstop("example-concurrent")
    assert data["outbound_syns"] == 150, data["outbound_syns"]
    assert not [d for d in data["unobserved_destinations"] if d.endswith(":443")], data
