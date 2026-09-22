# mcp-fanout

[![ci](https://github.com/marcosmatalab/mcp-fanout/actions/workflows/ci.yml/badge.svg)](https://github.com/marcosmatalab/mcp-fanout/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/marcosmatalab/mcp-fanout?include_prereleases)](https://github.com/marcosmatalab/mcp-fanout/releases)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

## Your proxy does not see your agent's traffic

A proxy selected by `HTTP_PROXY` and `HTTPS_PROXY` does not observe an agent's egress. It observes
the subset of its clients that chose to honour two environment variables, and that subset is not
knowable in advance. Here it silently excluded **one of the three components** that reached a third
party: that component completed 16 of 17 calls, returned the API's own answers, and recorded **zero
flows**. The packet capture caught it, not the proxy: ten connections going straight past. Full
chain in [`docs/THREATS.md`](docs/THREATS.md), threat 19.

Every repair to the instrument **lowered** the headline: **0.8947, then 0.8095, then 0.6579**,
against a threshold of 0.80 sealed before any measurement existed. A measurement whose headline
improves when its instrument does is measuring the instrument. This one did the opposite.

```bash
make install           # pip, once. The measurement core itself has no dependencies at all
make honesty-curve     # 0.05 s. No network, no keys, no Docker
```

![The honesty curve: the headline figure measured three times, 0.8947 then 0.8095 then 0.6579, falling below the pre-registered threshold of 0.80 as each blind spot in the instrument was removed](docs/figures/honesty-curve.svg)

## What you take away, even if you run nothing

1. **If you instrument agents with an environment-variable proxy, you are missing traffic.** Node's
   global `fetch` and `undici` do not honour those variables by default. The capability exists from
   Node 22.21 and 24.5, still off, turned on with `NODE_USE_ENV_PROXY=1`; an image running Node 20
   cannot see that traffic under any configuration.
2. **Packet capture is the only judge.** Anything going somewhere that is not the proxy is traffic
   your instrument is not reading. `make backstop` counts SYNs per destination, and that count is
   what found point 1.
3. **Attribution depends on the shape of the arguments, not on the tool.** A call committing two or
   more structural tokens attributes uniquely; one that commits a single token does not, under any
   rule that does not manufacture false attributions. Over 87 measured tool schemas: **38%** are
   attributable from the schema alone, **22%** never can be, **40%** are not knowable until a value
   is seen. `make argument-shapes`, no capture and no network.
4. **A pinned server is not pinned code.** `mcp-server-fetch`, pinned to an exact version and
   installed with `uvx`, pulls in ReadabiliPy, which runs `npm install` INSIDE the tool call: **41
   packages** from unpinned ranges, no lockfile, 87 registry requests one day and 82 the next. Two
   runs of the same pinned server can execute different code, and an egress allowlist for the npm registry allows everything that registry serves ([issue](https://github.com/alan-turing-institute/ReadabiliPy/issues/122), [issue](https://github.com/modelcontextprotocol/servers/issues/4830), threat 17).

![The observation chain: a tool call enters a server process, which can reach a third party through a proxy-honouring client, through Node's global fetch, or through a pinned client. The environment-variable proxy observes the first. The packet capture underneath observes all of them](docs/figures/observation-chain.svg)

## What this is, and what it is not

A **measurement**, not a product: six numbers built to decide whether a runtime tracing product is
worth building and which of two architectures it should have. What that product would be, and the
two categories it is deliberately not in, are in [`docs/METHOD.md`](docs/METHOD.md).

| It is | It is not |
| --- | --- |
| A harness that runs real MCP servers in a container and observes their egress | A gateway, a firewall, or anything that blocks traffic |
| An observer at the **own edge**: bytes leaving the local machine and bytes coming back | An injector: it never plants a marker, a token, or code inside a third party |
| A producer of aggregate counts, with a command behind every number | A dataset of who-calls-whom: it names no server and no organization in aggregate output |
| Digest-only: salted hashes and references, never captured content | A DLP product, a content archive, or a monitoring service |

Four standing rules shape that ([`docs/DOCTRINE.md`](docs/DOCTRINE.md)); the load-bearing one is
**never act on what is observed, only observe.** Hence an edge observer and not a marker travelling
the chain, which could not be passive and report at once. A chain deeper than the first
non-self-hostable node is unobservable without cooperation: physical limit, published as a result.

## What was measured, and on what

Two runs, published separately and never merged ([`docs/PROTOCOL.md`](docs/PROTOCOL.md)):
`20260919T115452Z-sequential`, 26 calls one at a time, which numbers 1 to 4 are read from, and
`20260919T194649Z-concurrent`, 130 calls in waves of 2, 5 and 10, the only pass number 5 may be read
from. Both are committed redacted under [`runs/`](runs/README.md), which is what makes every command
here work in a clean clone with no Docker, no network and no credentials.

**Ten pinned MCP servers, and the sample is smaller than ten.** Six are local by design and egress
nothing, the correct answer for them; one never starts without a key it was not given; three reach a
third party, and only two were visible to the proxy until the blind client above was found. So
numbers 1 and 2 rest on the **two** servers that egressed in the sequential pass and number 6 on the
**three** that did in the corrected concurrent one. Every server is pinned in
[`registry/servers.yaml`](registry/servers.yaml), schemas committed under `registry/probes/`. We do
not claim they are the ten most installed: nobody measured an install ranking here, and rule 6 says
a claim without a command does not get published.

## The six numbers

| # | Number | What it was asked to decide | Answer | Pass | Command |
| --- | --- | --- | --- | --- | --- |
| 1 | Outbound connections per tool call | Whether the causal union is trivial or is the product | raw p50 **0**, p95 **3**, max **84**; excluding package infrastructure p50 **0**, p95 **2**, max **3**. The median call reaches nothing; the maximum is one server installing a package mid-call (threat 17) | sequential | `make n1 RUN=example-sequential` |
| 2 | Distinct domains per tool call | The size of the publishable finding | p50 **0**, p95 **2**, max **3** | sequential | `make n2 RUN=example-sequential` |
| 3 | Servers propagating `traceparent` | Whether the cooperative path is worth anything today | **0** of **10** driven, and 0 of the **2** whose egress the proxy could see at all. The cheap fix nobody has adopted | sequential | `make n3 RUN=example-sequential` |
| 4 | Outbound bytes matching context files | Whether content matching has signal at all | **0** matched bytes, in every run. Nothing leaked, and the k-gram matcher is untouched by this work | sequential | `make n4 RUN=example-sequential` |
| 5 | Flows attributable to their causing call | **Whether the whole product works** | **0.6579** against a sealed **0.8**. **Not met**, and the product verdict was left unfrozen on purpose | concurrent | `make n5 RUN=example-concurrent` |
| 6 | Touched third parties that are self-hostable | How far the edge can advance before the chain breaks | **0.0** over **5** nodes. The recursion buys nothing here | concurrent | `make n6 RUN=example-concurrent` |

One command each, which is rule 6, and each defined in [`docs/METHOD.md`](docs/METHOD.md). Numbers
1 and 2 are read **only** from the sequential pass and number 5 **only** from the concurrent one:
with ten calls in flight "connections per call" is a figure about our own wave size; with one, the
strong attribution grade is unreachable by construction ([`docs/PROTOCOL.md`](docs/PROTOCOL.md)).
`make claims-check` fails if this table breaks that, and it has: number 1 was once published as
`p95 1` from the pass that may not answer, where the pass that may says **84**.

Number 5 was the decisive one and it is the one that failed. An instrument missing its own sealed
bar says the apparatus cannot settle the product question, not that the question is settled, so the
verdict was **left unfrozen on purpose**, a refusal itself inside the sealed block
([`docs/PREREG-F2.md`](docs/PREREG-F2.md), sections 8 and 16). Development stopped there. Every flow
carries three claims kept apart, occurrence, provenance and attribution in six grades, never joined
in one sentence ([`docs/DOCTRINE.md`](docs/DOCTRINE.md)).

## Quickstart

Python 3.11+. Docker is needed only for a new capture, the last command below; the rest run offline
against committed artifacts, and `make help` prints the full list.

```bash
make install                            # editable install with the dev extras
make reproduce                          # the headline number, end to end, from the committed runs
make numbers RUN=example-sequential     # or n1 .. n6, each from the pass that may publish it
make backstop RUN=example-concurrent    # outbound SYNs per destination: what the proxy could NOT see
make disclosure RUN=example-concurrent  # destinations nobody declared. Non-zero exit means stop
make gates                              # everything CI runs, in CI's order, in 61 seconds
make run                                # a NEW capture. The only one needing Docker and network
# make rarity and make control exit NON-ZERO as a result, not as a failure
```

## Reproducibility, privacy, disclosure

- **Reproducible at two levels.** Byte for byte: the core over fixtures, the calibration figures,
  and a run's normalized aggregate (`make verify`, `make figures-check`, `make reproduce`). **Not** a
  new capture, which contacts live third parties in an environment that changes between days: 87
  package-registry requests one day, 82 the next, same pinned server (threat 17). A finding, not a
  caveat.
- **Digest-only, and no captured run is ever committed.** Only salted shingle hashes and references
  ([`src/mcpfanout/redact.py`](src/mcpfanout/redact.py)). The two runs under `runs/example-*` are
  redacted copies, every server id, tool name and address replaced by a stable label, at the cost
  written down in [`runs/README.md`](runs/README.md).
- **Responsible disclosure, with a command.** `make disclosure` reduces a run's destinations to the
  ones nobody expected, per server, and exits non-zero. It does not decide the rule; it narrows a
  hostname dump to a short list to read documentation about (rule 7), and it names hosts, so its
  output stays in the untracked run directory.

## What was found in the measured environment

Two behaviours, both disclosed to their maintainers on 2026-09-19 with a publication window, before
any of this was written ([`docs/DISCLOSURE-LOG.md`](docs/DISCLOSURE-LOG.md)). One is point 4 above.
The other: a server whose embedded browser reaches destinations its documentation never declares,
established by a control run rather than by reading a hostname (threat 15).

## Status

Cost, measured rather than estimated: **0 EUR** of cloud compute and of paid APIs, one free-tier
GitHub token, **138 s** of driving across 21 capture runs, **two days** of wall clock. The money
cost is zero and the honest cost is attention ([`docs/PROTOCOL.md`](docs/PROTOCOL.md), part 3).

| Part | State |
| --- | --- |
| Measurement core, MCP stdio driver, mitmproxy addon and Docker harness | Implemented and unit-tested; the capture layer is runnable where Docker and network are, and is not exercised in CI |
| Server registry, probed schemas, and both call corpora | Ten servers pinned, schemas committed, corpora aligned against them and gated by tests |
| Phase A bench (the instrument) | Built, run, and passing its pre-registered sensor gate: capture recall 1.0, zero false strong attributions over 33 strong claims, false provenance 0.0 |
| F1, k-gram calibration on structured language | Complete. k chosen by the curve rather than by judgement, 0 of 224 reserved pairs at k = 22 against 66 of 224 at k = 16, rarity weighting measured and reverted because it did not lower the rate |
| F2, the structural matcher number 5 is read through | Complete and **failed its own sealed threshold**: pre-registered 0.80, measured **0.6579** |
| Phase C, attacking attribution adversarially | Not started, and named as what a measurement of this would need next. eBPF capture, which would catch pinned TLS, is out of scope and documented as the next layer |

**A pre-release is tagged and published, and `v1.0.0` follows on 19 October 2026**, when the
disclosure window closes: minting a DOI earlier would break a commitment made in writing. Cite the
archived release rather than the default branch, and take the current one from the badge above or
[releases/latest](https://github.com/marcosmatalab/mcp-fanout/releases/latest), never a tag named
in a sentence. **The DOI is minted with `v1.0.0`**, here and in [`CITATION.cff`](CITATION.cff).

## How this was built

One engineer, with Claude Code as the implementation tool, inside rules fixed **before** the first
commit rather than derived from what came out: four hard negatives, ten gate rules, and rule 6, no
published figure without a command that measures it ([`CLAUDE.md`](CLAUDE.md),
[`docs/DOCTRINE.md`](docs/DOCTRINE.md)). **48 of the first 50 commits carry a `Co-Authored-By`
trailer and every commit since does**, checked against the history by
`tests/test_history_claims.py` rather than asserted here.

The harness is the part worth judging: the measurements, the sealed thresholds and every disclosure
decision are the author's, and generated text is plausible faster than it is true, so the gates
exist to make it falsifiable before publishing. Rule 10 is the sharpest of them and earned its
place by being violated: **an instrument needs a test that fails when it is ABSENT, not only when it
is wrong.** Ten instances are recorded in [`docs/PROTOCOL.md`](docs/PROTOCOL.md), six outside the
measurement code: prose, figures, a version string, a release workflow, a gate and this history.
**Signing begins at `a167a54`**; earlier commits are deliberately not re-signed, because
back-signing replaces real provenance with manufactured provenance.

## Where to read next

| If you want | Read |
| --- | --- |
| A map of the documents, what each is for, how long it is, and the word budget | [`docs/README.md`](docs/README.md) |
| The instrument defect that outranks every other result | [`docs/THREATS.md`](docs/THREATS.md), threat 19 |
| What was predicted before measuring, including the prediction that was false | [`docs/PREREG-F2.md`](docs/PREREG-F2.md) |
| The gate, the phases, the two passes and the stop criteria | [`docs/PROTOCOL.md`](docs/PROTOCOL.md) |
| How the matcher was calibrated, and what the chosen k cost | [`docs/CALIBRATION.md`](docs/CALIBRATION.md) |
| What was disclosed, to whom and when, and how a finding about YOUR project would be handled | [`docs/DISCLOSURE-LOG.md`](docs/DISCLOSURE-LOG.md), [`SECURITY.md`](SECURITY.md) |
| How to run the gates locally, and what each one caught | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

## License

Apache-2.0. See [`LICENSE`](LICENSE).
