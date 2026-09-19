# mcp-fanout

A reproducible measurement harness that answers one question about MCP (Model Context
Protocol) servers: **when an agent makes a single tool call, how many third parties does
that call actually touch, and can each of those outbound connections be tied causally back
to the call that caused it?**

This repository is a **measurement**, not a product. It exists to produce six numbers.
Those numbers decide whether a runtime tracing product is worth building and, if so, which
of two very different architectures it should have. The rationale for measuring before
building is in [`docs/METHOD.md`](docs/METHOD.md): you cannot design the causal-union layer
without knowing the fan-out, and choosing blind means building the wrong one.

## What the eventual product would be, and what category it is not in

The harness measures. If the numbers support building something, that something is:

> **Runtime provenance and evidence for autonomous agents.**

MCP is the **first supported environment**, not the category. That distinction is the whole
positioning, and both of the obvious alternative framings are wrong in a way that costs money:

- **Not "MCP security".** It ties the product to one protocol that is still changing under it
  (the current revision removed the session, the handshake and three methods in a single
  release) and to a function that a gateway absorbs as a feature the moment it is worth having.
  A product whose category is a protocol dies when the protocol moves.
- **Not "data lineage".** That is Cyberhaven's category. They have the brand, the funding and
  the enterprise motion. Entering an occupied category with a smaller version of the incumbent's
  story is not a positioning, it is a comparison you lose by default.

What "runtime provenance and evidence" claims, and it is narrower than either of the above: at
the moment an autonomous agent acts, what left, where it went, and what evidence ties the two to
the action that caused it. Runtime rather than configuration, evidence rather than inference,
provenance rather than policy. The agent is the subject; the protocol it happens to speak is an
adapter.

## What this is, and what it is not

| It is | It is not |
| --- | --- |
| A harness that runs real MCP servers in a container and observes their egress | A gateway, a firewall, or anything that blocks traffic |
| An observer at the **own edge**: it watches bytes leaving the local machine and bytes coming back | An injector: it never plants a marker, a token, or code inside a third party |
| A producer of aggregate counts, with a command behind every number | A dataset of who-calls-whom; it names no server and no organization in aggregate output |
| Digest-only: it stores salted hashes and references, never captured content | A DLP product, a content archive, or a monitoring service |

The design follows four standing rules (the doctrine, [`docs/DOCTRINE.md`](docs/DOCTRINE.md)).
The one that shapes everything here: **never act on what is observed, only observe.** That
is why this is an edge observer and not a marker that travels the chain. A marker cannot be
passive and report at the same time, and a chain deeper than the first non-self-hostable node
is not observable by anyone without cooperation. That limit is physical, not an engineering
gap, and it is stated as a result rather than hidden.

## The six numbers

Each number has exactly one command that computes it (doctrine rule 6: no published number
without a command that measures it). Full definitions in
[`docs/THE-SIX-NUMBERS.md`](docs/THE-SIX-NUMBERS.md).

| # | Number | What it decides | Command |
| --- | --- | --- | --- |
| 1 | Outbound connections per tool call | Whether the causal union is trivial or is the product | `make n1` |
| 2 | Distinct domains per tool call | The size of the publishable finding | `make n2` |
| 3 | Fraction of servers that propagate `traceparent` | Whether the cooperative path (SEP-414) is worth anything today | `make n3` |
| 4 | Outbound bytes that literally match context files | Whether content matching has signal at all | `make n4` |
| 5 | Fraction of connections causally unifiable by content match | **Whether the whole product works** | `make n5` |
| 6 | Fraction of touched third parties that are themselves self-hostable | How far the edge can advance before the chain breaks | `make n6` |

Number 5 is the decisive one and the one nobody has measured. Numbers 1 to 4 are the paper;
number 5 is the viability. Number 6 sizes the recursion described in `docs/METHOD.md`.

## The evidence model: three separate claims

Every outbound connection carries three claims, recorded and reported separately. They are never
joined in one sentence, because a single word for all three is what the previous model did and it
could not answer any of them precisely. Full text in `docs/DOCTRINE.md`.

| Claim | Question it answers | Values |
| --- | --- | --- |
| Occurrence | was the transfer observed, and readable | `observed`, `connection_only` |
| Provenance | did the request carry recognisable material of ours | `none`, `context`, `arguments`, `both`, `unknown` |
| Attribution | could it be tied to a tool call, and how strongly | six grades, below |

Attribution is graded, strongest first. A grade claims a QUALITY OF EVIDENCE, never certainty of
cause.

| Grade | Evidence |
| --- | --- |
| `TRACE_PROPAGATED` | our exact W3C `traceparent` was in the outbound request |
| `CONTENT_UNIQUE` | several calls in flight, matched fragment present in exactly one |
| `CONTENT_AMBIGUOUS` | several calls in flight, fragment in several: content did not discriminate |
| `CONTENT_MATCH_UNCONTESTED` | a match with only one call in flight, so nothing was told apart |
| `TEMPORAL_ONLY` | a time window and a pid, nothing else |
| `UNATTRIBUTED` | no evidence, or ineligible, always with a named reason |

Strong attribution counts the first two only. `CONTENT_UNIQUE` requires more than one call in
flight, so **a sequentially driven run emits none, by construction, and a test asserts it.**
Anything else would publish the experimental setup as a result.

Which is why phase B is driven **twice**, and the two results are published separately and labelled
by pass (`docs/PHASES.md`):

| Pass | Command | Publishes | May not claim |
| --- | --- | --- | --- |
| Sequential, one call in flight | `make run` | numbers 1, 2, 3, 4 | anything about whether content discriminates |
| Concurrent, waves of N = 2, 5, 10 | `make run-concurrent` | number 5, split by N | any per-call fan-out figure |

Merging them would average two experimental conditions into one distribution, so the harness refuses
to write both into one run. Neither pass has ground truth and neither needs it: precision was
measured where it has a denominator, on the phase A bench.

The harness publishes the full distribution. That is measurement, not a promise.

## Quickstart

Requirements: Python 3.11+, Docker (for the capture run only). The measurement core (matching,
classification, aggregation) runs and is tested without Docker.

```bash
# 1. Install (editable) and dev deps
make install

# 2. Run the pure-Python core against synthetic fixtures and prove reproducibility
make verify

# 3. Phase B, sequential pass: one call in flight (needs Docker + network)
make run            # writes runs/<timestamp>-sequential/flows.jsonl

# 4. Phase B, concurrent pass: waves of N = 2, 5, 10, capped per server
make run-concurrent # writes runs/<timestamp>-concurrent/flows.jsonl. A SEPARATE run and figure

# 5. Compute all six numbers from the latest run
make numbers        # or make n1 ... n6 individually

# 6. Gate rule 7: which destinations nobody declared. Non-zero exit means stop and review
make disclosure
```

See [`docs/METHOD.md`](docs/METHOD.md) for the observation model and the capture layers,
[`docs/PHASES.md`](docs/PHASES.md) for the three phases and the two phase B passes, and
[`docs/THE-GATE.md`](docs/THE-GATE.md) for the nine conditions a run must pass before any number
is reported.

## Reproducibility, privacy, disclosure

- **Reproducible.** Two runs over the same corpus and the same pinned servers produce the same
  six numbers. `make verify` proves the measurement core is deterministic byte for byte over
  fixtures. Salt changes stored digests but never the numbers; see `docs/METHOD.md`.
- **Digest-only.** Payloads are never stored. The harness keeps salted shingle hashes and
  references. The sentence it can emit is: "the fragment with hash X, from reference Y, appeared
  in the output toward domain Z." See [`src/mcpfanout/redact.py`](src/mcpfanout/redact.py).
- **Responsible disclosure, with a command.** If a server egresses to a destination its
  documentation does not declare, the harness stops and flags it: `make disclosure` reduces a run's
  destinations to the ones nobody expected, per server, against
  `registry/declared-destinations.json`, and exits non-zero. It does not decide the rule (the
  declared set comes from tool schemas and stated purpose, not from a reading of each upstream
  README); it narrows a hostname dump to a short list to read documentation about. Its own output
  names hosts, so it stays in the untracked run directory. Nothing that locates a specific server is
  published until authorized. See [`docs/THE-GATE.md`](docs/THE-GATE.md) rule 7.

## Cost

The measurement is one afternoon and roughly 10 EUR of compute. It touches nothing outside a
container and starts no server against real credentials. The stop criteria in
[`docs/STOP-CRITERIA.md`](docs/STOP-CRITERIA.md) say when to stop spending.

## Status

This is `v0.1`: the honest state of each part.

| Part | State |
| --- | --- |
| Matching core (shingling, causal union, classification, aggregation) | Implemented and unit-tested |
| MCP stdio driver with `traceparent` in `_meta` | Implemented, tested against a mock server |
| mitmproxy capture addon and Docker harness | Implemented, runnable where Docker and network are available; not exercised in CI |
| Server registry (10 servers), pinned and probed | Every server's tool schemas measured and committed under `registry/probes/` |
| Per-server call corpora, sequential and concurrent | Both aligned against the real schemas and gated by tests |
| Phase A bench (the instrument) | Built, run, and passing its pre-registered sensor gate |
| Matcher calibration on structured language (`make fp`, `make ksweep`) | False-positive rate measured over 224 held-out pairs, and k chosen by the curve rather than by judgement: 0 of 224 at k = 22 against 66 of 224 at k = 16. Rarity weighting is the open piece |
| eBPF SSL uprobe capture (product-grade, catches pinned TLS) | Out of scope for the measurement, documented as the next layer |

## License

Apache-2.0. See [`LICENSE`](LICENSE).
