"""What happened with the first two DOIs, and the rule that followed, stay written where a release
is prepared and where a reader looks for how to cite.

The Zenodo webhook archives pre-releases as well as finals. The first two release candidates were
archived automatically when they were published, each with its own DOI, while CONTRIBUTING.md and
the README said the first DOI would be the final's. From the third candidate on, a candidate is
published with the webhook paused. That rule lives in a procedure a person follows by hand, so
what this file can check is that the procedure still carries the step and the command, and that
the documents state the two DOIs that exist rather than a DOI that does not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ARCHIVED_DOIS = ("10.5281/zenodo.22898049", "10.5281/zenodo.22901070")


def _flat(name: str) -> str:
    return " ".join((REPO / name).read_text(encoding="utf-8").split())


@pytest.mark.parametrize("name", ["README.md", "README.es.md", "CONTRIBUTING.md"])
def test_the_documents_name_the_two_dois_that_exist(name: str):
    text = _flat(name)
    missing = [doi for doi in ARCHIVED_DOIS if doi not in text]
    assert not missing, f"{name} does not state the archived candidate DOIs {missing}"


def test_the_release_procedure_pauses_the_webhook_for_a_candidate_and_restores_it():
    text = _flat("CONTRIBUTING.md")
    assert re.search(r"hooks/\S+ -F active=false", text), "no step pauses the Zenodo webhook"
    assert re.search(r"hooks/\S+ -F active=true", text), "no step reactivates the Zenodo webhook"
    assert text.index("active=false") < text.index("active=true")


def test_the_procedure_looks_the_webhook_up_rather_than_naming_its_id():
    """A hook id belongs to one installation of the integration. The procedure named 682045835, and
    reconnecting Zenodo gives the hook a new id, so the written command would have paused nothing
    and reported success. The id is looked up by the hook's target at the moment it is needed."""
    text = _flat("CONTRIBUTING.md")
    assert not re.search(r"hooks/\d+", text), "the release procedure names a webhook by a fixed id"
    assert 'contains("zenodo")' in text, "the procedure no longer says how to find the Zenodo hook"
