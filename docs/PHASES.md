# The three phases

The harness runs in three phases, in order, and the order is a gate, not a preference. Phase A is
the instrument. Phase B is the phenomenon. Phase C is the attack on our own method.

**Gate rule 8: the instrument passes before the phenomenon is measured.** No figure from phase B
may be published until phase A has passed the sensor gate below. An instrument that loses known
traffic produces numbers whose error is unknown, and an unknown error bar is not a measurement.
This is not a matter of confidence: it is that recall and precision have no denominator against
real servers, so a phase B run cannot tell you whether the sensor is working.

## Phase A: the controlled bench

Two or three MCP servers **we write ourselves**, with egress to destinations **we also own**. This
is the only configuration in which ground truth exists, because we caused every transfer and we
know what it contained.

Cases the bench has to generate, each one because some published figure depends on the sensor
handling it:

| Case | What it tests |
| --- | --- |
| One connection per call | the baseline. If this is wrong nothing else matters |
| Several connections per call | that fan-out is counted, not collapsed |
| Simultaneous connections | the only case where attribution is hard, and the only one that can earn `CONTENT_UNIQUE` |
| Unique arguments per call | that content discriminates when it can |
| Arguments repeated across concurrent calls | that it reports `CONTENT_AMBIGUOUS` instead of guessing |
| Payload in the body | the channel the matcher always had |
| Payload in the query string | the channel it was blind to until recently |
| Payload in a request header | a channel it is still blind to. Measured to size the gap |
| Reused connection pool | that one socket serving several calls does not break attribution |
| Retries | that a retried request is not counted as fresh fan-out |
| A task still alive after the response | egress after the call returned, which breaks any time window |

**Recall and precision can only be computed here.** Recall needs a denominator of transfers we
caused on purpose; precision needs a known cause to check a claim against. Neither exists for a
third-party server, so neither may be quoted from a phase B run.

### The subset built to fail

Part of the bench sends **the same data re-encoded**: base64, compressed, and JSON-escaped. The
sensor will miss all three, because matching is byte-literal and that is negative 3
(`docs/DOCTRINE.md`): we do not infer, so a re-encoded value is a false negative and we say so.

This subset exists **to measure how much is lost**, not to chase it. The output is a figure: the
fraction of known transfers that literal matching cannot see. It is documented as a **known
negative**, permanently, and never as debt. Calling it debt would imply a future version closes
it, and closing it means inferring, which is the one thing the project has decided not to do.

## Phase B: real servers

The ten pinned servers in `registry/servers.yaml`, with the corpus aligned against their real
schemas (`registry/probes/`, gated by `tests/test_corpus_matches_probes.py`). This phase measures
the phenomenon: fan-out, distinct domains, propagation, provenance coverage, attribution grades,
self-hostable fraction. It measures nothing about the instrument.

Blocked on phase A by gate rule 8.

## Phase C: attacking attribution

Concurrent calls, deliberately adversarial: the same fragment in several simultaneous calls,
fragments split across parameters, a server that pools connections across calls, a server that
delays egress past the response.

**This is the phase that answers the project's actual question.** Whether content matching
recovers attribution where time cannot is only answerable when time cannot, which means
concurrency. Under sequential driving the strongest content grade, `CONTENT_UNIQUE`, is
unreachable by construction (`docs/DOCTRINE.md`, the evidence model), and the code emits none and
a test asserts it emits none. Anything published before phase C describes what the harness sees
when attribution is easy.

## Pre-registered gates

Pre-registered means the thresholds are written **before** the data exists, so a disappointing
result cannot be re-framed as a pass after the fact.

### Sensor gate (phase A). Thresholds, because an instrument has a specification.

| Criterion | Threshold |
| --- | --- |
| Capture recall against known transfers | >= 95% |
| False strong attributions | **zero. Tolerance zero, not negotiable** |
| False provenance matches | < 1% |
| Normalized result reproducible across runs | required (gate rule 1) |

These thresholds need no market baseline to justify. An instrument that loses known traffic is
broken, and an instrument that claims a cause it did not have is worse than broken: one false
strong attribution destroys the evidentiary claim the whole product rests on, so the tolerance is
zero rather than small.

### Product gate (phase B). Directional, and deliberately WITHOUT a threshold.

There is no number here on purpose. Nobody has measured MCP fan-out or content-recoverable
attribution, so there is no baseline against which to set a bar, and a bar invented to look
rigorous would kill a good project or wave through a bad one with equal confidence. No figure is
written in this section, deliberately, because a number written here as an illustration is a
number someone lifts later as a target. `tests/test_doc_references.py` fails if one appears.

What is pre-registered instead:

1. The figure is published **whole and broken down**: every distribution, every grade, every
   named reason, no single headline ratio.
2. The go/no-go decision is **argued in writing against that figure**, and the argument is
   published with it.

A written argument against a published breakdown is auditable. An arbitrary threshold is not, it
just looks like it is.

### Stop gate

Stop if any of these holds. See also `docs/STOP-CRITERIA.md`.

- **Median fan-out of 1 with zero content matching.** Servers call their own API and nothing of
  the context leaves. The idea is real and the problem is small.
- **The target market is hosted remote MCP.** The observer can only watch the egress of a process
  it hosts, so a hosted-remote market is unobservable by this method, not merely harder.
- **Buyers consider their existing gateway sufficient.** Not a technical failure. It decides the
  same thing.
