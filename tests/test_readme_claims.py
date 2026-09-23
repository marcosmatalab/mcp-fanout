"""Every figure the README publishes must come from the pass that is allowed to publish it.

Gate 2 of the CI pipeline (`make claims-check`). It exists because the README published number 1
as `median 0, p95 1` and number 2 as `median 0, max 1`, and those two values exist only in the
CONCURRENT figure, which docs/PROTOCOL.md forbids quoting a per-call fan-out figure from. The
sequential pass, which is the one that may publish them, says p95 3 and max 84. The published
maximum was 1 and the real maximum was 84.

Nothing in the suite caught it: tests/test_doc_references.py checks that a referenced path exists,
never that a quoted number matches the artifact it is quoted from. This file closes that gap the
way gate rule 10 asks for, by reading the committed figure and comparing, rather than by checking
that the README has a table with the right shape.

Scope, deliberately narrow: it reads the README's six-number table and the committed normalized
aggregates under docs/figures/. It does not parse prose. A figure quoted in a sentence is out of
reach of a parser that must not produce false failures, and a gate that cries wolf gets disabled.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"
FIGURES = REPO / "docs" / "figures"

# The pass each number may be read from. Source of truth is the two-pass table in the protocol
# document; this dict is the machine-readable form of it and test_the_pass_rule_matches_the_protocol
# asserts the two agree, so editing one without the other fails.
PUBLISHABLE_BY = {
    1: "sequential",
    2: "sequential",
    3: "sequential",
    4: "sequential",
    5: "concurrent",
    6: "concurrent",
}

# Where a labelled statistic in an answer cell is to be looked up inside the number's figure
# entry. Number 1 publishes two distributions and the answer cell names which is which, so the
# segment the label appeared in decides the key. Anything not listed is checked by presence only.
STAT_KEYS = {
    1: {"raw": "connections_raw",
        "excluding package infrastructure": "connections_excluding_package_infrastructure"},
    2: {"": "distribution"},
}
STAT_LABELS = {"p50": "p50", "median": "p50", "p95": "p95", "max": "max"}

BOLD = re.compile(r"\*\*([^*]+)\*\*")
NUMBER_TOKEN = re.compile(r"^-?\d+(?:\.\d+)?$")


def _protocol_document() -> Path:
    """The gate, the phases and the stop criteria, in one file since they were merged."""
    candidate = REPO / "docs" / "PROTOCOL.md"
    assert candidate.exists(), "docs/PROTOCOL.md is missing; the pass rule lives in it"
    return candidate


def _readme_rows() -> list[dict[str, str]]:
    """The six-number table, as a list of cell dicts keyed by header.

    Located by its header rather than by line number: the README is rewritten often and a line
    number in a test is a second place to forget to update.
    """
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in README.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if header is None:
            lowered = [c.lower() for c in cells]
            if lowered[:2] == ["#", "number"] and "pass" in lowered and "command" in lowered:
                header = lowered
            continue
        if set("".join(cells)) <= set("- :"):
            continue
        row = dict(zip(header, cells, strict=False))
        if row.get("#", "").isdigit():
            rows.append(row)
    return rows


def _figure_for(pass_name: str) -> dict:
    """The committed aggregate for a pass, chosen by the run id the README names.

    Several runs of each pass exist under docs/figures/. The one that counts is the one the
    README says it measured, so the README's own claim about provenance is what selects the file
    the README's own numbers are checked against. If it names none, or names two, that is a
    failure and not a default: a reader cannot check a figure whose run is not stated.
    """
    readme = README.read_text(encoding="utf-8")
    found = []
    for path in sorted(FIGURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        provenance = data.get("provenance", {})
        if provenance.get("pass") != pass_name:
            continue
        if provenance.get("run_id", "") in readme:
            found.append((path, data))
    assert len(found) == 1, (
        f"expected exactly one {pass_name} figure whose run id the README names, got "
        f"{[str(p) for p, _ in found]}")
    return found[0][1]


def _entry(figure: dict, number: int) -> dict:
    entries = [n for n in figure["numbers"] if n["number"] == number]
    assert len(entries) == 1, f"number {number} appears {len(entries)} times in the figure"
    return entries[0]


def _values(node) -> set[str]:
    """Every scalar inside a figure entry, as text, for presence checks."""
    out: set[str] = set()
    if isinstance(node, dict):
        for value in node.values():
            out |= _values(value)
    elif isinstance(node, list):
        for value in node:
            out |= _values(value)
    else:
        out.add(str(node))
        if isinstance(node, float) and node.is_integer():
            out.add(str(int(node)))
    return out


def _sealed_constants() -> set[str]:
    """Numbers a README row may quote that are thresholds, not measurements.

    A pre-registered threshold is not in the figure by construction: it was written before the
    figure existed. It is read out of the pre-registration so that quoting a threshold nobody
    sealed still fails.
    """
    text = (REPO / "docs" / "PREREG-F2.md").read_text(encoding="utf-8")
    out = {"0.8"}
    out |= {m for m in re.findall(r"0\.\d+", text)}
    return out


def test_the_readme_has_the_six_number_table_with_a_pass_column():
    """The pass is part of the claim. Without it the reader cannot check the number at all."""
    rows = _readme_rows()
    assert [int(r["#"]) for r in rows] == [1, 2, 3, 4, 5, 6], (
        "the six-number table must exist, carry a `Pass` column and a `Command` column, and list "
        f"the numbers 1 to 6 in order; parsed: {[r.get('#') for r in rows]}")


def test_every_row_is_read_from_the_pass_that_may_publish_it():
    for row in _readme_rows():
        number = int(row["#"])
        stated = row["pass"].strip().lower()
        assert stated == PUBLISHABLE_BY[number], (
            f"number {number} is published as the {stated} pass; docs/PROTOCOL.md says it may "
            f"only be read from the {PUBLISHABLE_BY[number]} pass")


def test_every_command_names_the_run_of_the_pass_it_claims():
    """`make n1` with no RUN= reads whatever ran last, which is how the wrong pass gets quoted."""
    for row in _readme_rows():
        number = int(row["#"])
        command = row["command"]
        expected = f"RUN=example-{PUBLISHABLE_BY[number]}"
        assert expected in command, (
            f"number {number}'s command is `{command}`; it must pin the pass with {expected}, "
            "or a reader gets the numbers of whichever run happened to be last")


def test_every_labelled_statistic_matches_the_committed_figure():
    """p50, p95 and max are read out of the figure's own distribution, not out of prose."""
    problems = []
    for row in _readme_rows():
        number = int(row["#"])
        if number not in STAT_KEYS:
            continue
        figure = _figure_for(PUBLISHABLE_BY[number])
        entry = _entry(figure, number)
        answer = row["answer"]
        for segment_label, key in STAT_KEYS[number].items():
            segment = answer
            if segment_label:
                if segment_label not in answer:
                    problems.append(f"number {number}: the answer never says '{segment_label}'")
                    continue
                segment = answer.split(segment_label, 1)[1].split(";")[0]
            distribution = entry[key]
            for label, figure_key in STAT_LABELS.items():
                for stated in re.findall(rf"{label}\s+\*\*(-?\d+(?:\.\d+)?)\*\*", segment):
                    actual = distribution[figure_key]
                    if float(stated) != float(actual):
                        problems.append(
                            f"number {number}, {key}.{figure_key}: README says {stated}, "
                            f"{PUBLISHABLE_BY[number]} figure says {actual}")
    assert not problems, "\n".join(problems)


def test_every_bold_number_exists_in_the_figure_it_is_quoted_from():
    """A bold figure with no counterpart in the artifact is either stale or invented."""
    sealed = _sealed_constants()
    problems = []
    for row in _readme_rows():
        number = int(row["#"])
        figure = _figure_for(PUBLISHABLE_BY[number])
        present = _values(_entry(figure, number)) | sealed
        for token in BOLD.findall(row["answer"]):
            token = token.strip().rstrip(".,;:")
            if not NUMBER_TOKEN.match(token):
                continue
            if token in present:
                continue
            if token.rstrip("0").rstrip(".") in {p.rstrip("0").rstrip(".") for p in present}:
                continue
            problems.append(
                f"number {number}: the README publishes **{token}**, which appears nowhere in "
                f"the {PUBLISHABLE_BY[number]} figure's entry for that number")
    assert not problems, "\n".join(problems)


def test_the_pass_rule_matches_the_protocol():
    """The dict above is a copy of a rule written elsewhere. Copies drift; this one may not."""
    text = _protocol_document().read_text(encoding="utf-8")
    assert "numbers 1, 2, 3, 4" in text, (
        "the protocol document must still say which numbers the sequential pass publishes")
    assert re.search(r"number 5", text), "the protocol document must name number 5's pass"
    forbidden = [line for line in text.splitlines()
                 if "per-call fan-out" in line and "NOT" in line.upper()]
    assert forbidden, (
        "the protocol document no longer forbids a per-call fan-out figure from the concurrent "
        "pass; that prohibition is what this file enforces against the README")


def test_the_headline_attribution_figure_matches_the_concurrent_figure():
    """0.6579 is the number the whole repository is read for. It is checked on its own."""
    entry = _entry(_figure_for("concurrent"), 5)
    headline = str(entry["content_attributable_fraction"])
    assert headline in README.read_text(encoding="utf-8"), (
        f"the concurrent figure's content_attributable_fraction is {headline} and the README "
        "does not contain it")


# --- finding 1, the headline finding, against the committed run it is read from ---------------

BLIND_RUN = "example-blind-proxy"
FINDING_ONE = {
    "README.md": (r"completed (\d+) of (\d+) calls", r"\*\*(\d+) flows\*\*",
                  r"\*\*(\d+) connections\*\*"),
    "README.es.md": (r"completó (\d+) de (\d+) llamadas", r"\*\*(\d+) flujos\*\*",
                     r"\*\*(\d+) conexiones\*\*"),
}


def _backstop(run: str) -> dict:
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("tool_pcap_syns",
                                                  REPO / "tools" / "pcap_syns.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    pcap = REPO / "runs" / run / "backstop.pcap"
    out = module.syn_counts(pcap)
    out.update(module.run_view(pcap.parent, out["by_destination"]))
    return out


def test_finding_one_is_what_the_committed_blind_run_prints():
    """The finding quoted figures from a run nobody could re-run, and `make backstop` on the run
    the README named printed a different run whose 10 matched by coincidence. Every figure in the
    finding is now read back from the redacted run it comes from, and the command is named."""
    data = _backstop(BLIND_RUN)
    for name, (calls_re, flows_re, conns_re) in FINDING_ONE.items():
        raw = (REPO / name).read_text(encoding="utf-8")
        # The finding is a blockquote; its line markers would split "completed > 16" otherwise.
        text = " ".join(re.sub(r"^>\s?", "", raw, flags=re.M).split())
        assert f"make backstop RUN={BLIND_RUN}" in text, (
            f"{name} does not name the command that reproduces finding 1")
        calls, flows, conns = (re.search(p, text) for p in (calls_re, flows_re, conns_re))
        assert calls and flows and conns, f"{name} no longer states finding 1 in checkable form"
        completed, sent, silent = int(calls[1]), int(calls[2]), int(flows[1])
        assert any(row["completed"] == completed and row["calls"] == sent
                   and row["proxy_flows_during_calls"] == silent
                   for row in data["servers"].values()), (
            f"{name}: no server in {BLIND_RUN} completed {completed} of {sent} calls with "
            f"{silent} proxy flows while they ran: {data['servers']}")
        assert int(conns[1]) in data["unobserved_destinations"].values(), (
            f"{name}: {conns[1]} connections the proxy never saw is not in {BLIND_RUN}: "
            f"{data['unobserved_destinations']}")


HEADLINE = {"README.md": r"Your proxy saw only (\d+) of the (\d+) components",
            "README.es.md": r"Tu proxy solo vio (\d+) de los (\d+) componentes"}


def _observability(run_id: str) -> dict:
    figure = json.loads((FIGURES / f"{run_id}.json").read_text(encoding="utf-8"))
    return _entry(figure, 3)["observability"]


def test_the_finding_one_headline_states_the_measured_fraction():
    """The headline said "Your proxy does not see your agent's traffic" while the proxy saw two of
    the three components that reached a third party. It now states the fraction, and the fraction is
    read from the two committed figures: what the blind proxy observed, and how many components the
    corrected capture, which sees Node's fetch, found reaching a third party."""
    seen = _observability("20260919T193121Z-concurrent")["proxy_observed"]
    reached = _observability("20260919T194649Z-concurrent")["proxy_observed"]
    for name, pattern in HEADLINE.items():
        text = " ".join(re.sub(r"^>\s?", "", (REPO / name).read_text(encoding="utf-8"),
                               flags=re.M).split())
        found = re.search(pattern, text)
        assert found, f"{name}'s finding 1 headline does not state what the proxy saw"
        assert (int(found[1]), int(found[2])) == (seen, reached), (
            f"{name} says {found[1]} of {found[2]}; the figures say {seen} of {reached}")


SHAPES = {"README.md": r"\*\*(\d+)%\*\* of tools are attributable from the schema alone, "
                       r"\*\*(\d+)%\*\* never can be by content, \*\*(\d+)%\*\* depend",
          "README.es.md": r"el \*\*(\d+)%\*\* de las herramientas es atribuible solo con el "
                          r"esquema, el \*\*(\d+)%\*\* no lo es nunca por contenido y el "
                          r"\*\*(\d+)%\*\* depende"}


def test_the_argument_shape_percentages_are_what_the_tool_prints():
    """Finding 3 quoted 38 / 22 / 40 and nothing compared the prose with `make argument-shapes`.
    The 22 was wrong: eight tools with required arrays of strings were filed as never
    attributable."""
    import subprocess
    import sys
    out = subprocess.run([sys.executable, str(REPO / "tools" / "argument_shapes.py")],
                         cwd=REPO, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    expected = tuple(round(100 * data[k]["fraction"]) for k in (
        "attributable_by_schema_alone", "never_attributable_by_content",
        "undecided_until_a_value_is_seen"))
    for name, pattern in SHAPES.items():
        text = " ".join(re.sub(r"^>\s?", "", (REPO / name).read_text(encoding="utf-8"),
                               flags=re.M).split())
        found = re.search(pattern, text)
        assert found, f"{name} no longer states finding 3 in checkable form"
        assert tuple(int(g) for g in found.groups()) == expected, (
            f"{name} says {found.groups()}, make argument-shapes says {expected}")
