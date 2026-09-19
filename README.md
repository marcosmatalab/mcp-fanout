# mcp-fanout

A reproducible measurement harness that answers one question about MCP (Model Context
Protocol) servers: **when an agent makes a single tool call, how many third parties does
that call actually touch, and can each of those outbound connections be tied causally back
to the call that caused it?**

This repository is a **measurement**, not a product. It was built to produce six numbers that
would decide whether a runtime tracing product is worth building and, if so, which of two
architectures it should have. **The numbers were produced and the stop criteria fired**: see
[What it found](#what-it-found). The measuring apparatus did not meet the threshold sealed before
it was built, so the product verdict was left unfrozen on purpose rather than answered by an
instrument that had just failed. The rationale for measuring before building is in
[`docs/METHOD.md`](docs/METHOD.md): you cannot design the causal-union layer without knowing the
fan-out, and choosing blind means building the wrong one. That rationale held, and the thing it
protected us from turned out to be our own first two figures.

## What it found

Measured on run `20260919T194649Z-concurrent`: **ten widely used, pinned MCP servers**, 130 tool
calls in concurrent waves of 2, 5 and 10, plus a 26-call sequential pass. Every server is pinned
to an exact version in [`registry/servers.yaml`](registry/servers.yaml) and its tool schemas are
committed under `registry/probes/`. We do not claim they are the ten most installed: we never
measured an install ranking, and rule 6 says a claim without a command behind it does not get
published. Full write-up in
[`docs/paper/DRAFT.md`](docs/paper/DRAFT.md).

**The headline is about the instrument, not about MCP.**

> **A proxy selected by `HTTP_PROXY` and `HTTPS_PROXY` does not observe an agent's egress. It
> observes the subset of its clients that chose to honour two environment variables, and that
> subset is not knowable in advance.**

Node's global `fetch` ignores those variables unless `NODE_USE_ENV_PROXY=1` is set, and the
capability only exists from Node 22.21 and 24.5. Our image shipped Node 20, so no configuration
could have made that traffic visible. One of the three components that reached a third party was
invisible: it completed 16 of 17 calls, returned the API's own answers, and recorded **zero
flows**. The packet capture is what caught it, ten connections going straight past the proxy.
Full chain in [`docs/THREATS.md`](docs/THREATS.md) threat 19; count them yourself with
`make backstop`.

| result | value | command |
| --- | --- | --- |
| Connections per tool call, median | **0** | `make n1` |
| Context leakage: bait-file fragments in outbound requests | **zero bytes, across every run** | `make n4` |
| `traceparent` propagation | **0 of 3** observable components | `make n3` |
| **Attribution of a flow to its causing call** | **0.6579** against a sealed threshold of **0.80**: **not met** | `make n5` |
| Third parties that are themselves self-hostable | **0.0**: the recursion buys nothing | `make n6` |
| Tool schemas attributable from the schema alone | at most **38%** of 87 tools; 22% never can be | `make argument-shapes` |

**Three things worth knowing before reading any of those numbers.**

1. **Every repair to the instrument lowered the headline**: 0.8947, then 0.8095, then 0.6579, as
   blind spots were removed. A measurement whose headline improves as its instrument improves is
   measuring the instrument. `make honesty-curve`.
2. **Attribution depends on the shape of a call's arguments, not on the tool.** A call committing
   two or more structural tokens attributes uniquely; a call committing one does not, under any
   rule that does not manufacture false attributions. Measured inside a single component:
   repository reads attributed 3 of 3, searches whose query embedded a `repo:owner/name`
   qualifier 5 of 5, searches whose query was a bare phrase **0 of 6**.
3. **One of our own sealed predictions was false**, and it is still in the seal, unedited, with
   the correction beside it: [`docs/PREREG-F2.md`](docs/PREREG-F2.md).

**Two behaviours found in the measured environment**, both disclosed to their maintainers on
2026-09-19 with a publication window, before any of this was written:

- A tool call that runs `npm install` while it is running, pulling **41 packages** from unpinned
  ranges with no lockfile, in 82 registry requests one day and 87 the day before
  ([issue](https://github.com/alan-turing-institute/ReadabiliPy/issues/122),
  [issue](https://github.com/modelcontextprotocol/servers/issues/4830), threat 17).
- A server whose embedded browser reaches destinations its documentation never declares,
  established by a control run rather than by reading a hostname (threat 15).

## What the eventual product would be, and what category it is not in

The harness measured, and the stop criteria fired. The question it was built to inform was
whether to build:

> **Runtime provenance and evidence for autonomous agents.**

**The answer is not in this README, and that is deliberate.** The instrument failed its own
pre-registered threshold (0.6579 against 0.80), which says the measuring apparatus is not good
enough to settle the product question, not that the product question is settled. The product
verdict was therefore **left unfrozen on purpose**, and that refusal is itself inside the sealed
pre-registration block so it could not be replaced by a verdict once a result existed: see
[`docs/PREREG-F2.md`](docs/PREREG-F2.md) section 8, which names the two threats that made a
verdict from this sample unsound. Development stopped there.

The positioning below is what the product WOULD be, and it survives the negative result because
nothing measured here bears on the category choice.

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

These were questions. They now have answers, so the answers are in the table rather than the
questions.

| # | Number | What it was asked to decide | Answer | Command |
| --- | --- | --- | --- | --- |
| 1 | Outbound connections per tool call | Whether the causal union is trivial or is the product | median **0**, p95 **1**: on this sample the union is not the hard part | `make n1` |
| 2 | Distinct domains per tool call | The size of the publishable finding | median **0**, max **1** | `make n2` |
| 3 | Servers propagating `traceparent` | Whether the cooperative path is worth anything today | **0 of 3** observable. The cheap fix nobody has adopted | `make n3` |
| 4 | Outbound bytes matching context files | Whether content matching has signal at all | **zero bytes**. Nothing leaked, and the k-gram matcher is untouched by this work | `make n4` |
| 5 | Flows attributable to their causing call | **Whether the whole product works** | **0.6579** against a sealed **0.80**. **Not met**, and the product verdict was left unfrozen on purpose | `make n5` |
| 6 | Touched third parties that are self-hostable | How far the edge can advance before the chain breaks | **0.0**. The recursion buys nothing here | `make n6` |

Number 5 was the decisive one and it is the one that failed. Numbers 1 to 4 are the paper; number
6 sizes a recursion that turned out to have nothing to recurse into. The three denominators behind
number 5 are published together and never one alone, because this project has caught a
contaminated denominator three times; see [`docs/PREREG-F2.md`](docs/PREREG-F2.md) section 16.

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

# 7. What the proxy could NOT see: outbound SYNs per destination, from the pcap backstop.
#    Anything going somewhere that is not the proxy is traffic the instrument is not reading.
make backstop RUN=runs/<id>

# 8. The headline figure at each stage of the instrument becoming less blind
make honesty-curve

# 9. How much of a tool surface is attributable, from committed schemas alone. No capture needed
make argument-shapes

# 10. The F2 matcher's pre-registered predictions, on calibration material
make f2             # make f2-reserved measures the reserved half, ONCE, at the end
```

See [`docs/METHOD.md`](docs/METHOD.md) for the observation model and the capture layers,
[`docs/PHASES.md`](docs/PHASES.md) for the three phases and the two phase B passes, and
[`docs/THE-GATE.md`](docs/THE-GATE.md) for the **ten** conditions a run must pass before any
number is reported. Rule 10 was added last and earned its place by being violated: **every
instrument needs a test that fails when the instrument is ABSENT, not only when it is wrong.** A
wrong number gets investigated; a green gets published. There are five recorded instances, and the
fifth was this README, which for four days stated a cost, a reproducibility claim and a version
that the measurements contradicted.

## Reproducibility, privacy, disclosure

- **Reproducible, at two levels, and the distinction matters.** What reproduces byte for byte is
  the measurement CORE over fixtures (`make verify`) and the **normalized aggregate of a given
  run**, which is why aggregates are committed under `docs/figures/` while runs are not. What does
  **not** reproduce is a new capture: it contacts live third parties, and the measured environment
  changes between days. That is not a caveat, it is one of this project's findings, measured as 87
  package-registry requests on one day and 82 on the next from the same pinned server
  ([`docs/THREATS.md`](docs/THREATS.md) threat 17). An earlier version of this section claimed two
  runs produce the same six numbers. They do not. Salt changes stored digests but never the
  numbers; see `docs/METHOD.md`.
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

## Cost, measured rather than estimated

An earlier version of this section said "one afternoon and roughly 10 EUR of compute". Both
numbers were guesses and both were wrong, so here is what it actually cost.

| item | measured |
| --- | --- |
| Cloud compute | **0 EUR.** Everything runs in Docker on one machine. Nothing is billed |
| Paid APIs | **0 EUR.** One GitHub token on the free tier. Brave and Google Maps were rejected because their free tiers require a credit card ([`docs/LAB-ACCOUNTS.md`](docs/LAB-ACCOUNTS.md)) |
| Capture time across 21 runs | **138 seconds** of actual driving, the longest single run 25 s |
| Elapsed wall-clock | **two days**, not one afternoon |
| Disk | 1.8 GB image, 292 MB of untracked runs |

The money cost is genuinely zero and the honest cost is attention. It touches nothing outside a
container and starts no server against real credentials. The stop criteria in
[`docs/STOP-CRITERIA.md`](docs/STOP-CRITERIA.md) say when to stop spending.

## Status

**`v1.0.0` on release, 19 October 2026.** Not tagged yet: the disclosure window runs to that date and minting a DOI before it would break a commitment we made in writing ([`docs/paper/RELEASE-CHECKLIST.md`](docs/paper/RELEASE-CHECKLIST.md)). The honest state of each part:

| Part | State |
| --- | --- |
| Matching core (shingling, causal union, classification, aggregation) | Implemented and unit-tested |
| MCP stdio driver with `traceparent` in `_meta` | Implemented, tested against a mock server |
| mitmproxy capture addon and Docker harness | Implemented, runnable where Docker and network are available; not exercised in CI |
| Server registry (10 servers), pinned and probed | Every server's tool schemas measured and committed under `registry/probes/` |
| Per-server call corpora, sequential and concurrent | Both aligned against the real schemas and gated by tests |
| Phase A bench (the instrument) | Built, run, and passing its pre-registered sensor gate |
| F1: k-gram calibration on structured language (`make fp`, `make ksweep`, `make rarity`) | Complete, and it is NOT where the story ends. False-positive rate measured over 224 pairs, k chosen by the curve rather than by judgement (0 of 224 at k = 22 against 66 of 224 at k = 16), rarity weighting measured and reverted because it did not lower the rate |
| F2: the structural matcher that replaced the k-gram for number 5 (`make f2`) | Complete and **failed its own sealed threshold**. The k-gram missed 0.4615 of the calls that had literally caused the requests in front of it, because a call's arguments are structure and not prose. Structural containment over keyed token digests replaced it for number 5; number 4 kept the k-gram and its figures did not move by a byte. Pre-registered at 0.80, measured **0.6579** ([`docs/PREREG-F2.md`](docs/PREREG-F2.md)) |
| The negative corpora that gate both | Two halves retired after measurement and replaced, because a reserve loaded once is spent. A family built specifically to attack the structural matcher, since the original four were authored against the k-gram and cannot falsify it |
| eBPF SSL uprobe capture (product-grade, catches pinned TLS) | Out of scope for the measurement, documented as the next layer |

## Citing this

Cite the archived release rather than the default branch: the argument depends on the sealed
pre-registration block and on the signed commit history, and only a tag fixes both.

```
<!-- VERSION DOI: filled in from Zenodo in the commit that follows the release.
     The version DOI resolves to the exact deposit someone read; it belongs here and in
     CITATION.cff. -->
<!-- CONCEPT DOI: filled in at the same time, and it belongs HERE ONLY.
     It always resolves to the latest version, which is right for a reader arriving by link
     and wrong for a citation, which must point at what the author actually saw. -->
```

Machine-readable metadata is in [`CITATION.cff`](CITATION.cff). The release procedure, including
why Zenodo must be connected BEFORE the release is published, is in
[`docs/paper/RELEASE-CHECKLIST.md`](docs/paper/RELEASE-CHECKLIST.md).

## Where to read next

| If you want | Read |
| --- | --- |
| The result, in full | [`docs/paper/DRAFT.md`](docs/paper/DRAFT.md) |
| The instrument defect that outranks it | [`docs/THREATS.md`](docs/THREATS.md), threat 19 |
| What was predicted before measuring, including the prediction that was false | [`docs/PREREG-F2.md`](docs/PREREG-F2.md) |
| What was disclosed, to whom, and when | [`docs/DISCLOSURE-LOG.md`](docs/DISCLOSURE-LOG.md) |
| Why every instrument needs an absence test | [`docs/THE-GATE.md`](docs/THE-GATE.md), rule 10 |

## License

Apache-2.0. See [`LICENSE`](LICENSE).
