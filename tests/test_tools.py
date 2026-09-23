"""The `tools/` commands, exercised in process rather than only from the Makefile.

`tools/` was at 0% coverage with 720 statements, and it is where four published figures are
produced: the argument-shape distribution the README quotes, the honesty curve, both SVGs, and the
redaction that makes the committed example runs publishable. A figure whose producer is untested is
a figure whose producer can stop working in the one way that matters, silently, and still print
something well-formed.

Each test below asserts the VALUE the tool is supposed to compute, not that it ran: a renderer
that emitted an empty SVG and a redactor that copied its input unchanged would both exit zero.

`tools/` is not importable as a package, so each module is loaded by path the way the Makefile
invokes it. That is deliberate: importing them through a shim would test a shim.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import itertools
import json
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"


def _load(name: str) -> types.ModuleType:
    """Load a tool by path, as `make` does, with tools/ importable for its own siblings."""
    sys.path.insert(0, str(TOOLS))
    try:
        spec = importlib.util.spec_from_file_location(f"tool_{name}", TOOLS / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(TOOLS))


def _json_from(name: str, *args: str) -> tuple[int, dict]:
    """Run a tool's `main()` in process, with its argv, and parse what it printed.

    In process rather than through a subprocess so the lines actually execute under coverage: a
    tool exercised only through `subprocess` is a tool whose coverage is measured as zero, which
    is how `tools/` came to have 720 uncovered statements while four published figures went
    through it every day.
    """
    module = _load(name)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", [f"{name}.py", *args]):
        try:
            code = module.main()
        except SystemExit as exc:      # some tools exit through SystemExit, some return
            code = int(exc.code or 0)
    return code, json.loads(buf.getvalue())


def _stdout_json(name: str, *args: str) -> dict:
    return _json_from(name, *args)[1]


# --- the figures the README quotes ---------------------------------------------------------------

def test_argument_shapes_measures_every_committed_probe():
    """38% / 10% / 52% is a README claim, and this is the command behind it."""
    data = _stdout_json("argument_shapes")
    assert data["tools"] == 87
    assert data["attributable_by_schema_alone"]["fraction"] == 0.3793
    assert data["never_attributable_by_content"]["fraction"] == 0.1034
    total = (data["attributable_by_schema_alone"]["count"]
             + data["never_attributable_by_content"]["count"]
             + data["undecided_until_a_value_is_seen"]["count"])
    assert total == data["tools"], "the three buckets must partition the tool surface"


def _shape(schema: dict) -> str:
    return _load("argument_shapes").classify({"name": "planted", "inputSchema": schema})["shape"]


def test_a_structured_schema_can_be_one_the_matcher_cannot_attribute():
    """Constructed direction one: the rule counts it attributable and it is not. Two required
    strings, both enums of two-byte values, commit no structural token at all (MIN_TOKEN_BYTES is
    3), so no call of this tool can be attributed by content. The 38% therefore contains tools that
    are not attributable: it is a CEILING on attribution by schema, and it cannot be a lower
    bound."""
    from mcpfanout.structure import contains, tokens_of_arguments
    schema = {"type": "object", "required": ["unit", "lang"], "properties": {
        "unit": {"type": "string", "enum": ["C", "F"]},
        "lang": {"type": "string", "enum": ["en", "es"]}}}
    assert _shape(schema) == "structured"
    tokens = tokens_of_arguments({"unit": "C", "lang": "en"})
    assert tokens == frozenset() and not contains(tokens, frozenset({"C", "en"}))
    out = _stdout_json("argument_shapes")
    assert "this_is_a_CEILING_not_a_floor" in out["attributable_by_schema_alone"]
    assert "lower bound" not in out["what_this_is_not"], (
        "the tool calls the attributable share a lower bound, and the schema above is a tool the "
        "rule counts as attributable that the matcher can never attribute")


def test_a_schema_the_rule_calls_never_attributable_cannot_carry_a_token():
    """Constructed direction two: a required ARRAY of strings has no required string property, and
    the rule filed it under never attributable. The matcher walks every string leaf, arrays
    included, so a call to it commits tokens. `never` has to mean no string anywhere in the schema,
    which is the one case the matcher cannot produce a token from."""
    from mcpfanout.structure import tokens_of_arguments
    schema = {"type": "object", "required": ["paths"], "properties": {
        "paths": {"type": "array", "items": {"type": "string"}}}}
    assert tokens_of_arguments({"paths": ["/srv/reports/q3.txt"]}), "the matcher sees tokens"
    assert _shape(schema) != "no_string", "a schema that carries string leaves is not `never`"
    numbers_only = {"type": "object", "required": ["a"], "properties": {"a": {"type": "number"}}}
    assert _shape(numbers_only) == "no_string" and not tokens_of_arguments({"a": 2})


def test_the_honesty_curve_falls_at_every_step():
    """The shape IS the argument. A curve that stopped falling would be a different finding."""
    data = _stdout_json("honesty_curve")
    fractions = [p["fraction"] for p in data["points"]]
    assert fractions == [0.8947, 0.8095, 0.6579]
    assert data["every_observability_fix_lowered_the_headline"] is True
    assert all(a > b for a, b in itertools.pairwise(fractions))


def test_f2_reproduces_its_pre_registered_sections():
    data = _stdout_json("measure_f2")
    assert data["P4_regrade"]["strong"] >= 0
    assert "P4_regrade" in data and "command" in data


# --- the two SVGs, which are published figures drawn by code -------------------------------------

@pytest.mark.parametrize("tool,committed", [
    ("render_honesty_curve", "honesty-curve.svg"),
    ("render_chain_diagram", "observation-chain.svg"),
])
def test_the_renderers_reproduce_the_committed_svg_byte_for_byte(tool, committed):
    module = _load(tool)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), mock.patch.object(sys, "argv", [f"{tool}.py"]):
        assert module.main() == 0
    on_disk = (REPO / "docs" / "figures" / committed).read_text(encoding="utf-8")
    assert buf.getvalue() == on_disk, (
        f"docs/figures/{committed} is not what {tool}.py produces today. Run `make figures-check`: "
        "a picture is a published figure and a stale one is the defect that gate exists for")


def test_the_curve_svg_carries_the_data_and_both_themes():
    module = _load("render_honesty_curve")
    svg = module.render(module.curve_json())
    for value in ("0.8947", "0.8095", "0.6579"):
        assert f">{value}<" in svg, f"the curve does not plot {value}"
    assert "prefers-color-scheme: dark" in svg, (
        "the SVG has no dark-scheme block; referenced from a README it is its own document and "
        "would render black on black")
    assert "currentColor" not in svg, (
        "currentColor resolves to black inside an img tag, which is the bug this file had")
    assert "<title>" in svg and "<desc>" in svg, "the figure has no accessible description"


def test_the_curve_svg_captions_are_derived_from_the_data():
    """The caption under each point names the blind spot removed before it, from the figure."""
    module = _load("render_honesty_curve")
    data = module.curve_json()
    captions = module._captions(data["points"])
    assert len(captions) == len(data["points"])
    assert "fixed:" in captions[1] and "fixed:" in captions[2]
    assert "Node" in captions[2], "the last fix was the proxy-blind client, and the caption says so"


def test_the_chain_diagram_reads_its_count_from_the_committed_figure():
    module = _load("render_chain_diagram")
    figure = json.loads(module.FIGURE.read_text(encoding="utf-8"))
    expected = next(n for n in figure["numbers"] if n["number"] == 3)["observability"][
        "proxy_observed"]
    assert f"observed {expected} components" in module.render()


# --- the backstop and the redactor ----------------------------------------------------------------

def test_the_backstop_counts_syns_per_destination():
    data = _stdout_json("pcap_syns", "--run", "example-concurrent")
    assert data["outbound_syns"] == 150
    assert data["by_destination"], "a SYN count with no destinations is not a count"


def test_the_backstop_prints_what_the_proxy_and_the_driver_recorded(tmp_path):
    """Planted: one server completes calls with only a handshake flow, one destination is seen by
    SYN and by no flow, one is seen by both, and loopback is the proxy. Each must land where the
    finding needs it, or `make backstop` prints counts that cannot show threat 19."""
    module = _load("pcap_syns")
    calls = [{"server_id": "s-quiet", "ok": True}, {"server_id": "s-quiet", "ok": False},
             {"server_id": "s-seen", "ok": True}]
    flows = [{"server_id": "s-quiet", "phase": "handshake", "dest_ip": "192.0.2.10"},
             {"server_id": "s-seen", "phase": "driving", "dest_ip": "192.0.2.11"}]
    (tmp_path / "calls.jsonl").write_text("\n".join(json.dumps(c) for c in calls))
    (tmp_path / "flows.jsonl").write_text("\n".join(json.dumps(f) for f in flows))
    view = module.run_view(tmp_path, {"127.0.0.1:8080": 5, "192.0.2.11:443": 3,
                                      "192.0.2.99:443": 10})
    assert view["unobserved_destinations"] == {"192.0.2.99:443": 10}
    assert view["servers"]["s-quiet"] == {"calls": 2, "completed": 1, "proxy_flows": 1,
                                          "proxy_flows_during_calls": 0}
    assert view["servers"]["s-seen"]["proxy_flows_during_calls"] == 1


def test_the_backstop_refuses_a_run_with_no_pcap(tmp_path):
    module = _load("pcap_syns")
    with mock.patch.object(sys, "argv", ["pcap_syns.py", "--run", str(tmp_path)]), \
         pytest.raises(SystemExit) as exc:
        module.main()
    assert "backstop.pcap" in str(exc.value)


def test_the_link_layer_table_has_no_guessed_offset():
    """A wrong offset reports zero outbound connections, which reads as a finding."""
    module = _load("pcap_syns")
    assert module.L2_LEN[1] == 14, "Ethernet"
    assert module.L2_LEN[101] == 0, "DLT_RAW starts at the IP header; 4 belongs to DLT_NULL"
    assert module.L2_LEN[276] == 20, "LINUX_SLL2"


def test_the_redactor_replaces_every_identifier_and_keeps_every_digest(tmp_path):
    """The two halves of the contract, checked on a real run rather than on a fixture."""
    module = _load("redact_run")
    source = REPO / "runs" / "example-sequential"
    flows = [json.loads(line) for line in (source / "flows.jsonl").read_text().splitlines()]
    manifest = json.loads((source / "manifest.json").read_text())

    from mcpfanout.classify import PACKAGE_INFRASTRUCTURE_PATH, ExclusionList
    exclusions = ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH)
    red = module.Redactor(manifest, flows, exclusions)
    red.run_id = "example-sequential"
    red.learn_tools([json.loads(line)
                     for line in (source / "calls.jsonl").read_text().splitlines()])

    out = module.redact_flows(flows, red)
    assert len(out) == len(flows)
    for before, after in zip(flows, out, strict=True):
        assert after["dest_host"].startswith(("third-party-", "package-registry-", "loopback"))
        assert after["server_id"].startswith("server-")
        assert after["dest_ip"].startswith(("192.0.2.", "127.0.0.1"))
        # The digests and every counted quantity survive: that is what makes the numbers equal.
        assert after["matched_refs"] == before["matched_refs"]
        assert after["target_bytes"] == before["target_bytes"]
        assert after["ts"] == before["ts"]


def test_the_redactor_scrubs_an_error_message_but_keeps_the_protocol_code():
    module = _load("redact_run")
    scrubbed = module._scrub_error(
        "RuntimeError: tools/call error: {'code': -32603, 'message': 'Requires authentication'}")
    assert "-32603" in scrubbed
    assert "authentication" not in scrubbed.lower()
    assert module._scrub_error("") == ""
    assert "BRAVE" not in module._scrub_error(
        "EOFError: server closed stdout. stderr tail: ['Error: BRAVE_API_KEY is required']")


def test_the_redacted_pcap_is_a_well_formed_capture_with_documentation_addresses():
    syns = _load("pcap_syns")
    source = REPO / "runs" / "example-concurrent" / "backstop.pcap"
    counts = syns.syn_counts(source)
    assert counts["linktype"] == 1, "the committed backstop is Ethernet, which every reader parses"
    assert all(dest.startswith(("192.0.2.", "127.0.0.1")) for dest in counts["by_destination"])
    assert counts["outbound_syns"] == sum(counts["by_destination"].values())


# --- the generated halves of the negative corpus --------------------------------------------------

def test_the_generated_corpus_halves_are_re_derivable(capsys):
    """`make corpus-check`: the reserve must be generated, not hand-edited."""
    module = _load("build_negative_extras")
    with mock.patch.object(sys, "argv", ["build_negative_extras.py", "--check"]):
        assert module.main() == 0


def test_the_redactor_refuses_an_already_redacted_run(tmp_path):
    """A second pass cannot reproduce the first, so it is refused instead of approximated.

    The host classification is derived from hostnames and a redacted run has none, so
    `package-registry-a` would come back classified as a third party and numbers 1 and 5 would
    move. Silently producing that is the failure mode this repository keeps finding: a
    well-formed output from an absent input.
    """
    module = _load("redact_run")
    with mock.patch.object(sys, "argv", [
            "redact_run.py", "--run", str(REPO / "runs" / "example-concurrent"),
            "--out", str(tmp_path / "again")]), pytest.raises(SystemExit) as exc:
        module.main()
    assert "already a redacted run" in str(exc.value)
    assert not (tmp_path / "again").exists(), "the refusal wrote a partial run anyway"


def test_the_redactor_relabels_a_capture_end_to_end(tmp_path):
    """The whole pipeline over a capture-shaped run: hostnames in, class labels out.

    Built here rather than read from disk because the captures are not in the repository, and a
    test that could only run on the machine that took them is a test nobody else can run.
    """
    module = _load("redact_run")
    from mcpfanout.record import Flow, RunManifest, ToolCall, write_jsonl, write_manifest

    source = tmp_path / "capture"
    write_manifest(source / "manifest.json", RunManifest(
        run_id="20260101T000000Z-sequential", created="2026-01-01T00:00:00Z", salt_fixed=True,
        k=22, w=8, corpus_sha256="0" * 64, server_ids=["fetch", "github"],
        server_protocol_versions={"fetch": "2025-11-25", "github": "2024-11-05"},
        pass_name="sequential", servers_expecting_egress=["fetch", "github"],
        credential_presence={"github": {"GITHUB_PERSONAL_ACCESS_TOKEN": True}},
        tool_versions={"fetch": "2026.8.18"},
        notes="capture"))
    write_jsonl(source / "calls.jsonl", [
        ToolCall("20260101T000000Z-sequential", "fetch", "fetch-c000", "fetch", True, "00-a-b-01",
                 ok=False, error="RuntimeError: tools/call error: {'code': -32603, "
                                 "'message': 'Requires authentication'}"),
        ToolCall("20260101T000000Z-sequential", "github", "github-c000", "search_code", True,
                 "00-c-d-01"),
    ])
    write_jsonl(source / "flows.jsonl", [
        Flow("20260101T000000Z-sequential", "fetch", "fetch-c000", 1.0, "registry.npmjs.org",
             "104.16.0.34", "https", "GET", True, False, 42, 0, 0, 0, ["ref-1"], False, "none",
             "remote_leaf", True, phase="handshake"),
        Flow("20260101T000000Z-sequential", "github", "github-c000", 2.0, "api.github.com",
             "140.82.121.5", "https", "GET", True, False, 64, 12, 0, 0, [], True, "target",
             "remote_leaf", True, phase="driving"),
    ])

    out = tmp_path / "example-x"
    with mock.patch.object(sys, "argv",
                           ["redact_run.py", "--run", str(source), "--out", str(out)]), \
         contextlib.redirect_stdout(io.StringIO()) as buf:
        assert module.main() == 0
    summary = json.loads(buf.getvalue())
    assert summary["destination_labels"] == {"package-registry-a": "package_infrastructure",
                                             "third-party-a": "third_party"}

    text = (out / "flows.jsonl").read_text(encoding="utf-8")
    for vendor in ("npmjs", "github", "104.16", "140.82"):
        assert vendor not in text, f"the redacted flows still name {vendor}"
    flows = [json.loads(line) for line in text.splitlines()]
    assert flows[0]["dest_class"] == "package_infrastructure"
    assert flows[1]["dest_class"] == "third_party"
    assert flows[0]["matched_refs"] == ["ref-1"], "a digest reference was dropped"
    assert [f["server_id"] for f in flows] == ["server-0", "server-1"]

    calls = [json.loads(line) for line in (out / "calls.jsonl").read_text().splitlines()]
    assert [c["call_id"] for c in calls] == ["server-0-c000", "server-1-c000"]
    assert [c["tool_name"] for c in calls] == ["tool-0", "tool-0"]
    assert "-32603" in calls[0]["error"] and "authentication" not in calls[0]["error"]

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["credential_presence"] == {"server-1": {"secret-0": True}}
    assert manifest["redaction"]["source_run_id"] == "20260101T000000Z-sequential"
    assert "2026.8.18" not in json.dumps(manifest), "a version pin identifies a server on its own"
