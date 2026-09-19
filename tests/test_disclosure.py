"""Gate rule 7 as a checked rule: the declaration is complete, and the check never reads clean by accident.

Gate rule 7 says that if a server egresses to a destination its documentation does not declare, we
stop and flag it before publishing. The rule used to live only in prose, which means it was honoured
by reading a hostname list after a run and remembering what belongs there. That works for one server.

What these tests protect, in order of how badly each would fail:

1. **The declaration covers every server.** A server with no entry must come out
   `review_required`, never `clear`: "nothing is declared for it" and "everything it did was
   declared" are opposite findings and the check must not be able to confuse them.
2. **A missing declaration file is `undeterminable`, not `clear`.** Unevaluated is not satisfied,
   and a zero exit on a missing file would let the rule disappear silently.
3. **The call-supplied hosts stay in sync with the corpora.** Two of the servers fetch whatever host
   a call names, so their declared set is whatever our own corpus names. If the corpus starts naming
   another host and the declaration does not, the check would flag our own corpus as a finding, and
   a check that cries wolf on our own inputs is a check people learn to ignore.
4. **Every "known exception" cites a document that exists.** An exception with a dangling reference
   is an exception nobody wrote up, which is how a finding becomes permanently excused.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from mcpfanout.disclosure import (DECLARED_DESTINATIONS_PATH, UNKNOWN_SERVER, VERDICT_CLEAR,
                                  VERDICT_REVIEW, VERDICT_UNDETERMINABLE, DeclaredDestinations,
                                  check)

REPO = Path(__file__).resolve().parent.parent
DECLARED = REPO / DECLARED_DESTINATIONS_PATH


def _servers() -> list[dict]:
    return yaml.safe_load((REPO / "registry" / "servers.yaml").read_text())["servers"]


def _declared() -> DeclaredDestinations:
    d = DeclaredDestinations.load(DECLARED)
    assert d is not None
    return d


def _flow(server_id: str, host: str) -> SimpleNamespace:
    """The two fields the check reads. A real Flow has thirty; this asserts it needs only these."""
    return SimpleNamespace(server_id=server_id, dest_host=host)


def test_the_declaration_loads_and_cites_itself():
    d = _declared()
    cite = d.citation()
    assert cite["list_name"] == "declared-destinations"
    assert cite["version"], "a declaration with no version cannot be cited by a figure"
    assert cite["path"] == "registry/declared-destinations.json"
    assert len(cite["sha256"]) == 64
    # The citation is what may travel where hostnames may not, so it must carry none.
    assert "hosts" not in json.dumps(cite)


def test_every_registry_server_has_a_declaration():
    missing = [s["id"] for s in _servers() if s["id"] not in _declared().servers]
    assert not missing, f"no declared destinations for: {missing}"


def test_every_declaration_states_its_basis():
    for sid, decl in _declared().servers.items():
        assert len(decl.basis.strip()) > 60, f"{sid}: basis is missing or a shrug: {decl.basis!r}"


def test_known_exceptions_cite_a_document_that_exists():
    """A dangling reference turns a written-up finding into a permanent silent excuse."""
    for sid, decl in _declared().servers.items():
        for host, reference in decl.known_undeclared.items():
            paths = re.findall(r"\b(docs/[A-Za-z0-9_./-]+\.md)\b", reference)
            assert paths, f"{sid}/{host}: the exception cites no document"
            for rel in paths:
                assert (REPO / rel).is_file(), f"{sid}/{host}: {rel} does not exist"


def test_call_supplied_declarations_cover_every_host_the_corpora_name():
    """Their declared set IS our corpus, so the two cannot drift apart.

    Checked over both corpora, because the two passes drive different files and either one could
    introduce a host. A miss here would make the check flag our own inputs, which is the fastest way
    to train an operator to ignore a gate-rule banner.
    """
    declared = _declared()
    for server in _servers():
        decl = declared.servers.get(server["id"])
        if decl is None or not decl.call_supplied:
            continue
        text = ""
        for field in ("corpus_ref", "concurrent_corpus_ref"):
            if server.get(field):
                text += (REPO / server[field]).read_text()
        hosts = set(re.findall(r"https?://([A-Za-z0-9._-]+)", text))
        undeclared = sorted(h for h in hosts
                            if not any(h == d or h.endswith("." + d) for d in decl.hosts))
        assert not undeclared, (
            f"{server['id']}: the corpora name {undeclared}, which the declaration does not list. "
            f"Add the host to registry/declared-destinations.json or stop driving it.")


def test_a_declared_host_reads_clear():
    report = check([_flow("github", "api.github.com")], _declared())
    assert report["verdict"] == VERDICT_CLEAR
    assert report["servers"]["github"]["declared"] == ["api.github.com"]
    assert report["servers_to_review"] == []


def test_a_known_exception_reads_clear_and_carries_its_reference():
    report = check([_flow("fetch", "registry.npmjs.org")], _declared())
    assert report["verdict"] == VERDICT_CLEAR
    entry = report["servers"]["fetch"]
    assert entry["known"] == ["registry.npmjs.org"]
    assert "THREATS" in entry["known_references"]["registry.npmjs.org"]


def test_an_undeclared_host_requires_review():
    report = check([_flow("time", "telemetry.example.org")], _declared())
    assert report["verdict"] == VERDICT_REVIEW
    assert report["servers_to_review"] == ["time"]
    assert report["servers"]["time"]["new"] == ["telemetry.example.org"]
    assert "STOP" in report["gate_rule_7"]


def test_a_server_with_no_declaration_requires_review_rather_than_passing():
    """The failure that matters most: an unknown server must not read as a clean one."""
    report = check([_flow("a-server-we-never-declared", "api.example.org")], _declared())
    assert report["verdict"] == VERDICT_REVIEW
    entry = report["servers"]["a-server-we-never-declared"]
    assert entry["new"] == ["api.example.org"]
    assert "no declaration" in entry["reason"]


def test_egress_with_no_call_in_flight_is_still_attributed_to_a_bucket():
    """Unattributed egress to an undeclared host is the most interesting kind; it must not vanish."""
    report = check([_flow("", "api.example.org")], _declared())
    assert report["verdict"] == VERDICT_REVIEW
    assert UNKNOWN_SERVER in report["servers"]


def test_a_missing_declaration_is_undeterminable_and_never_clear():
    report = check([_flow("fetch", "example.net")], None)
    assert report["verdict"] == VERDICT_UNDETERMINABLE
    assert report["verdict"] != VERDICT_CLEAR
    assert "not the same as satisfied" in report["reason"]
    # The hosts are still reported, because the operator still has to look at them.
    assert report["servers"]["fetch"]["observed_hosts"] == ["example.net"]


def test_a_connection_with_no_host_is_counted_apart_from_destinations():
    """A non-HTTP flow has no host: "we could not see where it went" is not "it went nowhere"."""
    report = check([_flow("fetch", ""), _flow("fetch", "example.net")], _declared())
    assert report["connections_without_a_host"] == 1
    assert report["servers"]["fetch"]["observed_hosts"] == ["example.net"]


def test_the_report_declares_itself_operator_only():
    report = check([_flow("fetch", "example.net")], _declared())
    assert "gate rule 3" in report["_operator_only"]


def test_no_disclosure_report_is_committed_under_docs():
    """It names servers and hosts, so docs/ is exactly where it may never appear (gate rule 3)."""
    offenders = [str(p.relative_to(REPO)) for p in (REPO / "docs").rglob("*.json")
                 if "disclosure" in p.name or "_operator_only" in p.read_text()]
    assert not offenders, f"an operator-only report is committed: {offenders}"
