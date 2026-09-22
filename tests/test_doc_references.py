"""Every docs/ path referenced from code or from another doc must exist.

Written because the evidence-model commit cited a governance document one commit before it
existed. A
dangling reference in a governance document is worse than a missing section: it reads as though
the rule is written down somewhere, so nobody writes it.

Deliberately narrow: it checks repository-relative paths that look like project files, and does
not try to validate URLs, anchors, or prose. A link checker that needs the network cannot run in
`make verify`, and one that parses anchors would fail on ordinary English containing a slash.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEARCHED = ("src", "docs", "harness", "tests", "registry")
# Repository-relative paths under a known top-level directory with a known extension. The
# examples are written with angle brackets on purpose: a path-shaped example in this file would
# be picked up by the scan below, which reads every file including this one.
#   docs/<name>.md, registry/<name>.json, src/<pkg>/<mod>.py, tests/<name>.py
PATH_RE = re.compile(r"\b((?:docs|registry|corpus|harness|tests|src)/[A-Za-z0-9_./-]+"
                     r"\.(?:md|json|py|ya?ml|sh))\b")


def _files_to_scan() -> list[Path]:
    out: list[Path] = []
    for top in SEARCHED:
        for path in sorted((REPO / top).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".md", ".sh", ".yaml", ".yml"):
                if "__pycache__" in path.parts or ".egg-info" in str(path):
                    continue
                out.append(path)
    for name in ("README.md", "CLAUDE.md", "Makefile", "pyproject.toml"):
        if (REPO / name).is_file():
            out.append(REPO / name)
    return out


def _references() -> dict[str, set[str]]:
    """Referenced repo path -> the files that reference it."""
    found: dict[str, set[str]] = {}
    for path in _files_to_scan():
        text = path.read_text(encoding="utf-8", errors="replace")
        for ref in PATH_RE.findall(text):
            found.setdefault(ref, set()).add(str(path.relative_to(REPO)))
    return found


def test_every_referenced_repo_path_exists():
    missing = {}
    for ref, sources in sorted(_references().items()):
        # A glob is a pattern, not a path: registry/probes/*.json is satisfied by the directory.
        target = REPO / ref
        if "*" in ref:
            if not (REPO / ref).parent.is_dir():
                missing[ref] = sorted(sources)
            continue
        if not target.exists():
            missing[ref] = sorted(sources)
    assert not missing, "referenced but absent:\n" + "\n".join(
        f"  {ref}  <- {', '.join(src)}" for ref, src in missing.items())


def test_the_protocol_document_carries_the_gate_the_phases_and_the_stop_criteria():
    """Gate rule 8 is a claim about the ORDER of two things, so both have to be in one place.

    This used to check that two documents pointed at each other, which is the weaker property: two
    documents that cross-reference correctly can still disagree, and they did. They are one file
    now, so the check is that the file still contains every part the rule spans.
    """
    protocol = (REPO / "docs" / "PROTOCOL.md").read_text()
    assert "rule 8" in protocol.lower(), "the protocol must name the rule that enforces the order"
    for phase in ("Phase A", "Phase B", "Phase C"):
        assert phase in protocol, f"{phase} is missing from docs/PROTOCOL.md"
    for part in ("## Part 1: the gate", "## Part 2: the three phases",
                 "### Product gate", "### Stop gate"):
        assert part in protocol, f"{part!r} is missing from docs/PROTOCOL.md"
    # The ten gate rules, by their numbering, so a merge that dropped one fails here.
    for rule in range(1, 11):
        assert f"\n{rule}. **" in protocol or f"\n{rule:>2}. **" in protocol, (
            f"gate rule {rule} is missing from docs/PROTOCOL.md")


THRESHOLD_HEADING = "Thresholds, because an instrument has a specification."


def _sensor_gate_rows() -> dict[str, str]:
    """The sensor gate's THRESHOLD table, as criterion -> threshold.

    Anchored on the threshold heading and not on "### Sensor gate", because the document now also
    carries a measured-result section under a similar heading. A parser that grabbed the first
    match would read the results table and silently stop checking the commitments, which is the
    failure mode this whole file exists to prevent.
    """
    protocol = (REPO / "docs" / "PROTOCOL.md").read_text()
    assert protocol.count(THRESHOLD_HEADING) == 1, "the threshold table's heading is not unique"
    section = protocol.split(THRESHOLD_HEADING)[1].split("### Product gate")[0]
    rows = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and not set(cells[0]) <= set("- "):
            rows[cells[0].lower()] = cells[1]
    return rows


def test_the_sensor_gate_thresholds_are_written_down():
    """Pre-registered means the numbers exist before the data. Absent, they get invented later."""
    rows = _sensor_gate_rows()
    recall = next(v for k, v in rows.items() if "recall" in k)
    provenance = next(v for k, v in rows.items() if "provenance" in k)
    assert "95%" in recall
    assert "1%" in provenance
    assert any("reproducible" in k for k in rows)


def test_false_strong_attribution_tolerance_stays_at_zero():
    """Read from the threshold cell itself, not from the surrounding prose.

    The first version of this test looked for the word "zero" anywhere in the document, so
    softening the table row to "under 2%" passed: the prose beside the table still said zero.
    One false strong attribution destroys the evidentiary claim the product rests on, so this is
    the one threshold that must be read out of the cell that defines it.
    """
    rows = _sensor_gate_rows()
    cell = next(v for k, v in rows.items() if "strong attribution" in k)
    assert "zero" in cell.lower(), cell
    assert "not negotiable" in cell.lower(), cell
    assert not re.search(r"\d",
        cell), f"a numeric tolerance appeared where zero is required: {cell}"


def test_the_product_gate_has_no_invented_threshold():
    """A bar with no baseline behind it kills good projects and passes bad ones equally well."""
    protocol = (REPO / "docs" / "PROTOCOL.md").read_text()
    product = protocol.split("### Product gate")[1].split("### Stop gate")[0]
    assert "WITHOUT a threshold" in product or "without a threshold" in product
    # No percentage may appear in the product-gate section at all.
    assert not re.search(r"\d+\s*%", product), (
        "a threshold appeared in the product gate; it was pre-registered as having none")


DOCS_INDEX = REPO / "docs" / "README.md"


def test_the_docs_index_lists_every_document_and_sizes_it_correctly():
    """A map of the documentation is a published figure too, and it goes stale the same way.

    Rounded to the nearest hundred words, because a reader uses the number to decide what to open
    and a test that demanded exact counts would fire on every edit without telling anyone anything.
    """
    index = DOCS_INDEX.read_text(encoding="utf-8")
    documents = sorted(p for p in (REPO / "docs").glob("*.md") if p.name != "README.md")
    assert documents, "docs/ has no documents"
    problems = []
    for path in documents:
        if path.name not in index:
            problems.append(f"{path.name} is not listed in docs/README.md")
            continue
        actual = len(path.read_text(encoding="utf-8").split())
        row = next(line for line in index.splitlines() if path.name in line)
        quoted = re.search(r"\| ([\d,]+) words \|", row)
        if not quoted:
            problems.append(f"{path.name} is listed without a size")
            continue
        stated = int(quoted.group(1).replace(",", ""))
        if abs(stated - actual) > 100:
            problems.append(f"{path.name}: index says {stated} words, the file has {actual}")
    assert not problems, "\n".join(problems)
