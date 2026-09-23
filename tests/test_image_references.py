"""Every document that names the harness image names the one this repository builds.

docs/THREATS.md told a reader to reproduce threat 17 with `mcp-fanout-harness:0.1.0`, a tag the
repository had stopped building two versions earlier. The command looked runnable and failed with
"image not found", which reads as the reader's mistake rather than the document's. The image is
built by harness/docker-compose.yml, and that file is the single source of its name and tag; every
other mention is a copy, and this file fails when a copy disagrees.

What is scanned: every tracked text file except harness/docker-compose.yml (the source) and
tests/ (which plant wrong tags on purpose). Captured runs are not tracked, so they are not in it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = "harness/docker-compose.yml"
IMAGE = re.compile(r"\bmcp-fanout-harness:([0-9A-Za-z][0-9A-Za-z._-]*)")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yml", ".yaml", ".toml", ".cff", ".txt", ""}


def built_tag() -> str:
    tags = IMAGE.findall((REPO / SOURCE).read_text(encoding="utf-8"))
    assert len(set(tags)) == 1, f"{SOURCE} must build exactly one harness tag, found {tags}"
    return tags[0]


def stale_references(paths: list[str], tag: str) -> dict[str, list[str]]:
    """path -> the harness tags it names that are not the one built."""
    found: dict[str, list[str]] = {}
    for path in paths:
        if path == SOURCE or path.startswith("tests/") or Path(path).suffix not in TEXT_SUFFIXES:
            continue
        file = REPO / path
        if not file.is_file():
            continue
        wrong = sorted({t.rstrip(".") for t in IMAGE.findall(
            file.read_text(encoding="utf-8", errors="replace"))} - {tag})
        if wrong:
            found[path] = wrong
    return found


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.splitlines()


def test_no_document_names_a_harness_image_the_repository_does_not_build():
    tag = built_tag()
    found = stale_references(_tracked(), tag)
    assert not found, (
        f"the repository builds mcp-fanout-harness:{tag} ({SOURCE}); these name another tag:\n"
        + "\n".join(f"  {p}: {', '.join(t)}" for p, t in found.items()))


def test_the_check_finds_a_planted_stale_tag(tmp_path: Path, monkeypatch):
    """Rule 10: a scanner that stopped matching would report every document as clean."""
    name = "docs/" + "planted" + ".md"
    (tmp_path / "docs").mkdir()
    (tmp_path / name).write_text("docker run mcp-fanout-harness:0.1.0 -lc 'x'. Or "
                                 "mcp-fanout-harness:9.9.9.\n")
    monkeypatch.setattr("test_image_references.REPO", tmp_path)
    assert stale_references([name], "9.9.9") == {name: ["0.1.0"]}
