"""The browser control: the comparison that turns a diagnosis into an attribution of cause.

Gate rule 7 flagged destinations on a server that embeds a headless browser, and the plausible
reading was that the browser produced them on its own. `src/mcpfanout/control.py` exists so that
reading has to be measured: a bare browser, same binary, same flags, same proxy, no MCP server.

What these tests protect, in order of how badly each would fail:

1. **A verdict is never reached by omission.** Reproduced, partial, not reproduced and
   nothing-under-review are four different outcomes and the one that permits publishing an
   attribution is the narrowest of them. A comparison that returned "reproduced" because the list
   of hosts under review was empty would authorise exactly the claim it was built to check.
2. **A named artifact cannot exist without its authorisation.** Gate rule 3 forbids naming a
   server in anything published; rule 7 describes the one path where naming is allowed, and it
   runs through a disclosure. The publishable form refuses without that record rather than
   emitting an empty field.
3. **The launcher's destinations stay out of it.** A package registry contacted before the server
   process existed is npm's traffic, and letting it into a comparison about a browser would put a
   host in "only under the server" that no browser could ever reproduce.
4. **The control's launch flags do not drift from the server's.** The control is only a control
   while it launches the same browser the same way, and the flags live in two files for a reason
   the comment in each one states. This is the guard that makes two copies safe.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcpfanout.control import (CONTROL_SERVER_ID, VERDICT_NOT_REPRODUCED,
                               VERDICT_NOTHING_TO_EXPLAIN, VERDICT_PARTIAL, VERDICT_REPRODUCED,
                               compare, publishable)
from mcpfanout.record import PASS_CONTROL, PASSES, PASSES_MEASURING_A_SERVER, PHASE_DRIVING, PHASE_HANDSHAKE

REPO = Path(__file__).resolve().parent.parent


def flow(host, *, server_id="puppeteer", phase=PHASE_DRIVING, target_matched=0, body_matched=0,
         causal=False):
    return SimpleNamespace(dest_host=host, server_id=server_id, phase=phase,
                           target_matched_bytes=target_matched, body_matched_bytes=body_matched,
                           causal=causal)


# --- 1. The four verdicts, and the fact that none of them is reachable by omission.

def test_every_reviewed_host_reproduced_is_the_only_reproduced_verdict():
    control = [flow("clients2.example", server_id=CONTROL_SERVER_ID),
               flow("accounts.example", server_id=CONTROL_SERVER_ID)]
    subject = [flow("clients2.example"), flow("accounts.example"), flow("example.net")]
    out = compare(control, subject, "puppeteer", ["clients2.example", "accounts.example"])
    assert out["verdict"] == VERDICT_REPRODUCED
    assert out["not_reproduced_by_the_bare_browser"] == []


def test_one_host_the_browser_did_not_reach_downgrades_the_whole_verdict():
    """The dangerous failure: a partial result reading as a clean attribution.

    If the browser explains one host and not the other, the unexplained one is still a finding
    about the server, and a pooled "yes" would bury it under the explained one.
    """
    control = [flow("clients2.example", server_id=CONTROL_SERVER_ID)]
    subject = [flow("clients2.example"), flow("telemetry.example")]
    out = compare(control, subject, "puppeteer", ["clients2.example", "telemetry.example"])
    assert out["verdict"] == VERDICT_PARTIAL
    assert out["not_reproduced_by_the_bare_browser"] == ["telemetry.example"]


def test_a_browser_that_reached_none_of_them_refutes_the_diagnosis():
    control = [flow("example.net", server_id=CONTROL_SERVER_ID)]
    subject = [flow("telemetry.example")]
    out = compare(control, subject, "puppeteer", ["telemetry.example"])
    assert out["verdict"] == VERDICT_NOT_REPRODUCED


def test_an_empty_review_list_is_its_own_verdict_and_not_a_pass():
    """Nothing under review must not read as "the control explained everything".

    This is the omission failure: with no hosts to explain, every host is trivially explained, and
    a boolean verdict would come out true for a comparison that measured nothing.
    """
    out = compare([flow("a.example", server_id=CONTROL_SERVER_ID)], [flow("a.example")],
                  "puppeteer", [])
    assert out["verdict"] == VERDICT_NOTHING_TO_EXPLAIN
    assert out["verdict"] != VERDICT_REPRODUCED


def test_the_verdict_carries_its_own_meaning():
    """A verdict string in a report nobody can read is a verdict that gets misquoted."""
    out = compare([], [flow("a.example")], "puppeteer", ["a.example"])
    assert out["verdict_means"]


# --- 2. Naming an instance requires the authorisation that gate rule 7 demands.

def test_the_publishable_form_refuses_without_an_authorisation_record():
    out = compare([flow("a.example", server_id=CONTROL_SERVER_ID)], [flow("a.example")],
                  "puppeteer", ["a.example"])
    with pytest.raises(ValueError, match="authorisation"):
        publishable(out, control_run_id="c", subject_run_id="s", repetitions=3,
                    dwell_seconds=12.0, url_source="corpus/calls/puppeteer.json",
                    authorisation="   ")


def test_the_publishable_form_says_it_names_an_instance():
    """A committed file that names a server must say so in the file, not only in a directory name.

    Everything else under docs/figures/ names nothing, and a reader who finds a hostname in one of
    them is right to treat it as a leak unless the artifact itself declares the exception.
    """
    out = compare([flow("a.example", server_id=CONTROL_SERVER_ID)], [flow("a.example")],
                  "puppeteer", ["a.example"])
    art = publishable(out, control_run_id="c", subject_run_id="s", repetitions=3,
                      dwell_seconds=12.0, url_source="corpus/calls/puppeteer.json",
                      authorisation="Marcos Mata, 2026-09-19, docs/DISCLOSURE-LOG.md")
    assert art["names_an_instance"] is True
    assert art["authorisation"]
    assert "control-compare" in art["provenance"]["command"]


# --- 3. The launcher's traffic is not the server's, and not the browser's either.

def test_handshake_destinations_are_excluded_from_both_sides():
    """A package registry reached before any call cannot be reproduced by a browser, ever.

    Letting it in would put it in "only under the server" and make every comparison look partial,
    which is the same separation disclosure.check makes and for the same reason.
    """
    subject = [flow("registry.npmjs.example", phase=PHASE_HANDSHAKE), flow("a.example")]
    out = compare([flow("a.example", server_id=CONTROL_SERVER_ID)], subject,
                  "puppeteer", ["a.example"])
    assert "registry.npmjs.example" not in out["subject"]["hosts"]
    assert out["only_under_the_server"] == []


def test_other_servers_flows_are_not_counted_as_the_subjects():
    subject = [flow("a.example"), flow("b.example", server_id="fetch")]
    out = compare([], subject, "puppeteer", ["a.example"])
    assert set(out["subject"]["hosts"]) == {"a.example"}


def test_the_control_reports_whether_our_own_arguments_appeared_on_the_wire():
    """The control publishes the corpus call's digests, so it asks the same matching question.

    A background request carrying our argument material would be a far more serious finding than
    the one under investigation, and the comparison has to be able to show it rather than hide it
    behind a host list.
    """
    control = [flow("clients2.example", server_id=CONTROL_SERVER_ID, target_matched=22)]
    out = compare(control, [flow("clients2.example")], "puppeteer", ["clients2.example"])
    ctx = out["control"]["matching"]["context_channel"]
    assert ctx["flows_with_a_match"] == 1
    assert ctx["target_matched_bytes"] == 22


def test_the_two_channels_are_never_pooled_into_one_number():
    """Context bytes and argument hits are different quantities and one of them has no byte count.

    Summing them would produce a figure that reads as "how much of our material travelled" and is
    not that for either channel. The published shape has to keep them addressable.
    """
    out = compare([flow("a.example", server_id=CONTROL_SERVER_ID, target_matched=30)],
                  [flow("a.example", causal=True)], "puppeteer", ["a.example"])
    for side in ("control", "subject"):
        m = out[side]["matching"]
        assert set(m) == {"flows", "context_channel", "argument_channel"}
        assert "matched_bytes" not in m, "the pooled field is back; the channels are conflated"
    assert out["subject"]["matching"]["argument_channel"]["causal_flows"] == 1


def test_the_control_declares_whether_its_own_matcher_was_alive():
    """Zero matches only means something if something COULD have matched.

    The control navigates to the corpus URL with the corpus call's digests published, so that
    navigation should be causal. If it is not, "the background requests carried nothing" is
    indistinguishable from "the matcher saw nothing at all", in the direction that flatters the
    diagnosis.
    """
    dead = compare([flow("a.example", server_id=CONTROL_SERVER_ID)], [flow("a.example")],
                   "puppeteer", ["a.example"])
    assert dead["control"]["matching"]["argument_channel"]["is_the_sensor_alive"] is False
    alive = compare([flow("example.net", server_id=CONTROL_SERVER_ID, causal=True),
                     flow("a.example", server_id=CONTROL_SERVER_ID)],
                    [flow("a.example")], "puppeteer", ["a.example"])
    assert alive["control"]["matching"]["argument_channel"]["is_the_sensor_alive"] is True


def test_the_reviewed_hosts_answer_the_content_question_one_by_one():
    """Whether a flagged host carried our material decides what the finding IS.

    A background beacon carrying nothing is a note. The same host carrying a fragment of a tool
    call's arguments is the phenomenon the six numbers exist to measure, and the two must not be
    answerable only by a pooled figure over the whole run.
    """
    subject = [flow("a.example", causal=True), flow("b.example")]
    out = compare([], subject, "puppeteer", ["a.example", "b.example"])
    carried = out["did_the_reviewed_hosts_carry_our_material"]
    assert carried["a.example"]["under_the_server"]["argument_channel"]["causal_flows"] == 1
    assert carried["b.example"]["under_the_server"]["argument_channel"]["causal_flows"] == 0


# --- 4. The control is only a control while it launches the same browser the same way.

def test_the_control_flags_match_the_flags_the_registry_records_for_the_server():
    """Two copies of the launch flags, and this is what makes that safe.

    The control cannot import them from registry/servers.yaml without the measurement core gaining
    a YAML dependency, so they are transcribed, and a transcription with no drift guard is a
    future capture where the control launched a different browser process than the server did.
    """
    import sys
    sys.path.insert(0, str(REPO / "harness"))
    from control_browser import SERVER_BROWSER_FLAGS

    registry_text = (REPO / "registry" / "servers.yaml").read_text(encoding="utf-8")
    puppeteer_block = registry_text.split("- id: puppeteer", 1)[1].split("\n  - id:", 1)[0]
    for flag in SERVER_BROWSER_FLAGS:
        assert flag in puppeteer_block, (
            f"{flag} is in the control's flag list but not in the registry's record of what the "
            f"server launches with; one of the two has drifted")


def test_the_control_reads_its_target_from_the_corpus_and_does_not_carry_its_own():
    """A control navigating somewhere else is not the control for the call under investigation."""
    import sys
    sys.path.insert(0, str(REPO / "harness"))
    from control_browser import navigation_target

    url, arguments = navigation_target(REPO / "corpus" / "calls" / "puppeteer.json")
    corpus = json.loads((REPO / "corpus" / "calls" / "puppeteer.json").read_text())
    assert url == corpus[0]["arguments"]["url"]
    assert arguments == corpus[0]["arguments"]
    source = (REPO / "harness" / "control_browser.py").read_text(encoding="utf-8")
    assert "https://example" not in source, "the control carries a hard-coded target"


def test_a_control_run_is_labelled_a_pass_but_never_a_measuring_one():
    """The label is what stops a control run being read as a measurement of a server.

    It has no tool calls, so every per-call figure over it divides by zero, and `make numbers`
    would pick it up as the latest run without this separation.
    """
    assert PASS_CONTROL in PASSES
    assert PASS_CONTROL not in PASSES_MEASURING_A_SERVER


def test_the_aggregate_refuses_a_control_run(tmp_path, capsys):
    """The refusal is a command's behaviour, not a note in a docstring."""
    from mcpfanout.cli import main
    from mcpfanout.demo import build_demo_run
    from mcpfanout.record import read_manifest, write_manifest

    build_demo_run(tmp_path)
    manifest = read_manifest(tmp_path / "manifest.json")
    manifest.pass_name = PASS_CONTROL
    write_manifest(tmp_path / "manifest.json", manifest)
    with pytest.raises(SystemExit) as exc:
        main(["aggregate", "--run", str(tmp_path)])
    assert "control" in str(exc.value)
    assert "control-compare" in str(exc.value)


def test_the_run_id_of_a_control_capture_says_what_it_is():
    """A directory listing has to separate a control from a pass without opening either."""
    run_sh = (REPO / "harness" / "run.sh").read_text(encoding="utf-8")
    assert re.search(r'CONTROL.*==.*1.*\]\]; then LABEL="control"', run_sh) or \
           'LABEL="control"' in run_sh


def test_the_liveness_field_exists_run_wide_and_not_per_host():
    """Sliced to one host, "nothing matched" IS the answer, not a statement about the sensor.

    A liveness flag in that slice reads as "the matcher was dead for this host", which is not a
    thing that can happen, and it would turn the answer the comparison exists to give into a
    suspicion about the instrument.
    """
    out = compare([flow("example.net", server_id=CONTROL_SERVER_ID, causal=True),
                   flow("a.example", server_id=CONTROL_SERVER_ID)],
                  [flow("a.example")], "puppeteer", ["a.example"])
    assert "is_the_sensor_alive" in out["control"]["matching"]["argument_channel"]
    per_host = out["did_the_reviewed_hosts_carry_our_material"]["a.example"]
    for side in ("under_the_server", "in_the_control"):
        assert "is_the_sensor_alive" not in per_host[side]["argument_channel"]
        assert per_host[side]["argument_channel"]["causal_flows"] == 0


# --- 5. The committed comparison and the prose that quotes it cannot drift apart.

def _committed_comparisons():
    return sorted((REPO / "docs" / "figures" / "control").glob("*.json"))


@pytest.mark.parametrize("path", _committed_comparisons(), ids=lambda p: p.name)
def test_a_committed_comparison_declares_its_authorisation_and_its_run(path):
    """The one family of published artifacts that names an instance carries its permission slip.

    Everything else under docs/figures/ is checked to name nothing. This directory is the
    exception gate rule 7 describes, and an exception that cannot point at its own disclosure is
    indistinguishable from a leak.
    """
    doc = json.loads(path.read_text())
    assert doc["names_an_instance"] is True
    assert doc["authorisation"].strip()
    assert "DISCLOSURE-LOG" in doc["authorisation"]
    assert doc["provenance"]["control_run_id"] and doc["provenance"]["subject_run_id"]
    assert "control-compare" in doc["provenance"]["command"]
    assert doc["verdict"] in {VERDICT_REPRODUCED, VERDICT_PARTIAL, VERDICT_NOT_REPRODUCED,
                              VERDICT_NOTHING_TO_EXPLAIN}


@pytest.mark.parametrize("path", _committed_comparisons(), ids=lambda p: p.name)
def test_the_disclosure_log_carries_an_entry_for_every_named_artifact(path):
    """A named instance whose disclosure was never written up is the thing rule 7 forbids."""
    log = (REPO / "docs" / "DISCLOSURE-LOG.md").read_text(encoding="utf-8")
    doc = json.loads(path.read_text())
    assert doc["subject"]["server_id"] in log, (
        f"{path.name} names a server with no entry in docs/DISCLOSURE-LOG.md")
    for host in doc["under_review"]:
        assert host in log, f"{path.name} names {host}, which the disclosure log does not mention"


def test_threat_15_quotes_the_committed_comparison_and_not_a_memory():
    """The prose and the artifact are one claim, so they fail together or not at all.

    Same guard tests/test_committed_figures.py puts on the six-number artifacts, applied to the
    one figure that is allowed to name a server.
    """
    threats = (REPO / "docs" / "THREATS.md").read_text(encoding="utf-8")
    block = threats.split("\n15. ", 1)[1].split("\n16. ", 1)[0]
    path = REPO / "docs" / "figures" / "control" / "20260919T125335Z-control-vs-puppeteer.json"
    doc = json.loads(path.read_text())
    assert path.name in block, "threat 15 does not cite the artifact it rests on"
    assert doc["verdict"] in block
    for host in doc["under_review"]:
        assert host in block, f"threat 15 does not name {host}, which it is the finding about"
    assert str(doc["provenance"]["repetitions"]) in block
    assert not doc["only_under_the_server"], (
        "the artifact now has a destination the browser does not explain, and threat 15 still "
        "says it has none")
    assert doc["control"]["matching"]["argument_channel"]["is_the_sensor_alive"] is True, (
        "threat 15 rests on a control whose matcher never fired, which cannot support it")
    assert str(doc["control"]["matching"]["flows"]) in block
