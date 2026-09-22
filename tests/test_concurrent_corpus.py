"""The concurrent-pass corpus: valid against the real schemas, and deliberately NOT distinctive.

Two halves, and the second is the unusual one.

The first half is the same requirement the sequential corpus has (see
`tests/test_corpus_matches_probes.py`, whose validator this file reuses rather than copying): every
tool exists on the server, every argument validates against the committed probe schema, and every
entry says why it is there. A call to a tool that does not exist records zero egress and biases the
numbers downward with nothing in the output saying so.

The second half enforces the REALISM RULE, which is the exact inverse of the bench's fragment rule.
`tests/test_bench_metrics.py` fails if any two fragments in a discriminating wave share a k-gram,
because a bench whose fragments collide measures its own collisions. This corpus fails if the
arguments DO NOT collide, because a corpus whose arguments are artificially distinct replicates the
bench on a real server and measures something already known (`corpus/concurrent/README.md`,
`docs/PROTOCOL.md` phase B, prediction B1).

"Realistic" cannot be asserted directly. What can be asserted is its mechanical consequence: real
arguments sent by one agent in one wave share structure, so at least one pair of calls per server
must share a 16-byte run. That is a weak test of a strong claim, and it is the strongest form of it
that a test can hold: it cannot prove the corpus is realistic, but it fails the moment someone
"fixes" the ambiguity by making the arguments unique, which is the failure that would quietly turn
this pass back into the bench.
"""

import json
from pathlib import Path

import pytest
import yaml
from test_corpus_matches_probes import CANARY, META_KEYS, _strings, _validate

from mcpfanout.redact import Redactor

ROOT = Path(__file__).resolve().parent.parent
CONCURRENT_DIR = ROOT / "corpus" / "concurrent"


def _registry() -> dict:
    return yaml.safe_load((ROOT / "registry" / "servers.yaml").read_text())


def _servers() -> list[dict]:
    return _registry()["servers"]


def _ids() -> list[str]:
    return [s["id"] for s in _servers()]


def _load(server: dict) -> tuple[list[dict], dict[str, dict]]:
    corpus = json.loads((ROOT / server["concurrent_corpus_ref"]).read_text())
    probe = json.loads((ROOT / server["probe_ref"]).read_text())
    return corpus, {t["name"]: t for t in probe["tools"]}


def _digest_sets(corpus: list[dict], k: int) -> list[frozenset[str]]:
    """Each call's argument k-gram digests, exactly as the driver publishes them.

    Built through the same serialisation the driver uses (``json.dumps(..., sort_keys=True)`` in
    ``driver.args_digests_for``) rather than a re-implementation, because the overlap this test
    measures is overlap in the bytes the ADDON compares, not in the prose.
    """
    r = Redactor(salt=b"mcp-fanout/test/concurrent-corpus", k=k)
    out = []
    for call in corpus:
        args = call.get("arguments", {})
        if not args:
            out.append(frozenset())
            continue
        out.append(r.kgram_digest_set(json.dumps(args, sort_keys=True).encode()))
    return out


# --- Half one: the same alignment the sequential corpus has.

@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_every_server_declares_a_concurrent_corpus_that_exists(server):
    assert server.get("concurrent_corpus_ref"), f"{server['id']}: no concurrent_corpus_ref"
    assert (ROOT / server["concurrent_corpus_ref"]).is_file(), server["concurrent_corpus_ref"]


def test_no_orphan_corpus_files():
    """A file nobody drives is a corpus that looks measured and is not."""
    declared = {Path(s["concurrent_corpus_ref"]).name for s in _servers()}
    on_disk = {p.name for p in CONCURRENT_DIR.glob("*.json")}
    assert on_disk == declared, (f"orphans: {sorted(on_disk - declared)}, "
                                 f"missing: {sorted(declared - on_disk)}")


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_every_tool_exists_on_the_server(server):
    corpus, tools = _load(server)
    assert corpus, f"{server['id']}: empty concurrent corpus drives nothing"
    unknown = sorted({c["tool"] for c in corpus} - set(tools))
    assert not unknown, (f"{server['id']}: tools not offered by the server: {unknown}. "
                         f"Offered: {sorted(tools)}")


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_every_argument_validates(server):
    corpus, tools = _load(server)
    errors: list[str] = []
    for i, call in enumerate(corpus):
        tool = tools.get(call["tool"])
        if tool is None:
            continue  # reported by the test above; do not double-report
        _validate(call.get("arguments", {}), tool["inputSchema"],
                  f"{server['id']}[{i}] {call['tool']}", errors)
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_every_entry_states_why(server):
    corpus, _ = _load(server)
    for i, call in enumerate(corpus):
        assert call.get("why", "").strip(), f"{server['id']}[{i}] {call['tool']}: no 'why'"
        extra = set(call) - META_KEYS
        assert not extra, f"{server['id']}[{i}]: unrecognised corpus keys {sorted(extra)}"


# --- Half two: the realism rule, and the concurrency it has to support.

@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_the_corpus_supports_at_least_the_first_rung(server):
    """A concurrent pass needs at least two calls in flight, or it is the sequential pass.

    Checked against the DECLARED cap as well as the corpus length, because a cap of 1 would make
    the run silently sequential while the manifest called it concurrent.
    """
    corpus, _ = _load(server)
    cap = int(server.get("max_concurrency", 0))
    assert cap >= 2, f"{server['id']}: max_concurrency {cap} cannot hold a wave"
    assert len(corpus) >= 2, f"{server['id']}: {len(corpus)} calls cannot fill a wave of 2"


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_the_cap_carries_its_reason(server):
    """A cap without a reason is a knob someone turns later to get a nicer number."""
    why = (server.get("max_concurrency_why") or "").strip()
    assert len(why) > 40, f"{server['id']}: max_concurrency_why is missing or a shrug: {why!r}"


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_the_corpus_is_not_artificially_distinct(server):
    """At least one pair of calls must share a k-gram. The realism rule, mechanically.

    This is the inverse of the bench's precondition, and it fails in the direction that matters: if
    a future edit makes every argument unique to "improve" the discrimination figure, the pass stops
    measuring realistic material and this test says so.
    """
    corpus, _ = _load(server)
    k = int(_registry().get("k", 16))
    sets = _digest_sets(corpus, k)
    sharing = [(i, j) for i in range(len(sets)) for j in range(i + 1, len(sets))
               if sets[i] & sets[j]]
    assert sharing, (
        f"{server['id']}: no two calls share a {k}-byte run, so this corpus is as distinctive as "
        f"the bench's keyed fragments. Realistic arguments share structure; see "
        f"corpus/concurrent/README.md")


@pytest.mark.parametrize("server", _servers(), ids=_ids())
def test_no_planted_canary_in_the_concurrent_corpus(server):
    """The sequential corpus plants a canary; this one must not, and the reason is the experiment.

    The same marker in N concurrent calls makes every flow match every call, so every grade would be
    CONTENT_AMBIGUOUS by construction: our marker, not the servers' behaviour. A unique marker per
    call is the bench. Either way the pass would measure its own corpus.
    """
    corpus, _ = _load(server)
    planted = [c["tool"] for c in corpus
               if any(CANARY in s for s in _strings(c.get("arguments", {})))]
    assert not planted, (f"{server['id']}: the canary is planted in {planted}; the concurrent pass "
                         f"matches on real argument text (corpus/concurrent/README.md)")


def test_the_two_corpora_are_different_files():
    """Driving the sequential corpus under concurrency would make the pass a duplicate, not a pass.

    """
    for server in _servers():
        assert server["corpus_ref"] != server["concurrent_corpus_ref"], server["id"]
