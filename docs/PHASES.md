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

## Phase B: real servers, driven TWICE

The ten pinned servers in `registry/servers.yaml`, with both corpora aligned against their real
schemas (`registry/probes/`, gated by `tests/test_corpus_matches_probes.py` and
`tests/test_concurrent_corpus.py`). This phase measures the phenomenon: fan-out, distinct domains,
propagation, provenance coverage, attribution grades, self-hostable fraction. It measures nothing
about the instrument.

Phase A passed the sensor gate, which is what gate rule 8 required. **Phase B is still blocked, by
gate rule 9**: the matcher's false-positive rate on structured language has to be measured and
published before any volume figure is, because phase A measured that rate over keyed digests and
real arguments are natural language and URLs that share structure. See `docs/CALIBRATION.md`, which
also carries the three pieces of that work and which of them are done.

### Why two passes and not one

One sequential pass cannot measure the thesis, and the reason is arithmetic rather than a matter
of degree. `CONTENT_UNIQUE` requires `active_calls_in_window > 1` (`match.grade_attribution`, and
that requirement is the whole defence against the tautology). Driven one call at a time, every
window holds exactly one call, so the strong-attribution fraction of a sequential phase B run is
**0.0 by construction**, for every server, whatever the servers do. Running phase B that way would
not measure the thesis; it would make it unobservable again, with a published figure of zero that
reads like a finding.

But the reverse is also true, and it is why concurrency is not simply switched on for everything:
numbers 1 and 2 are **per invocation**. With ten calls in flight, "connections per call" is a
figure about our own wave size and the attribution of a connection to a call is exactly what is
in question, so a per-call distribution measured under concurrency would be circular.

So the two conditions are driven as two runs, and each publishes only what it can answer:

| | Sequential pass | Concurrent pass |
| --- | --- | --- |
| Command | `make run` | `make run-concurrent` |
| Corpus | `corpus/calls/` | `corpus/concurrent/` |
| In flight per server | 1 | N on the ladder 2, 5, 10, capped per server |
| Publishes | numbers 1, 2, 3, 4 | number 5: the grade distribution, split by N |
| Its attribution grades are | `CONTENT_MATCH_UNCONTESTED` by construction, reported as such | the measurement |
| May NOT claim | anything about whether content discriminates | any per-call fan-out figure |
| Ground truth | none, and none needed | none, and none needed: precision was measured on the bench |

**The two figures are published separately and labelled by pass.** The label is in the manifest
(`record.PASSES`), in the run directory's name, in the aggregate output (`"pass"`), and in the
committed artifact's provenance. `harness/drive_all.py` refuses to drive a second pass into a run
that already holds one: merging them would average two experimental conditions into one
distribution, and no footnote undoes that arithmetic afterwards.

**Why no ground truth in the concurrent pass, and why that is not a hole.** Precision needs a known
cause, which exists only where we caused the transfer, which is phase A. That is where it was
measured: zero false strong attributions over 33 strong claims. The concurrent pass asks a
different question, the one phase A cannot answer, which is how the grades come out on traffic
nobody designed. Adding a fabricated ground truth here would mean planting a unique marker per
call, which is the bench again (`corpus/concurrent/README.md`).

**The ladder is the bench's ladder**, N = 2, 5 and 10, capped per server by `max_concurrency` with
its reason in the registry. Same rungs on purpose: the bench established what the sensor does at
those levels with maximally distinctive fragments, so any difference measured here is a difference
in the material, not in the level.

**The corpus rule, which is the inverse of the bench's.** The bench requires that no two fragments
share a 16-byte run. This corpus requires the opposite: arguments that look like what an agent
would really send, which means they share domains, path prefixes, parameter names and common words.
Made artificially distinct, the concurrent pass would replicate the bench on a real server and
measure something already known. `tests/test_concurrent_corpus.py` fails if the corpus is pairwise
k-gram-disjoint, which is the mechanical form of that rule.

### Pre-registered predictions for the concurrent pass

Written **2026-09-19, before the first concurrent run existed**, for the same reason the sensor
gate's thresholds were: a disappointing result must not be re-framed as a pass afterwards, and a
surprising one must be surprising against something written down. The block below is frozen by
digest in `tests/test_phase_b_prediction.py`, so editing it after the data arrives fails the suite.

<!-- PREREGISTERED:BEGIN -->

**B1. Discrimination on real servers will be WORSE than on the bench, and the failure mode will be
`CONTENT_AMBIGUOUS` rather than a false attribution.**

Mechanism: the bench's fragments are keyed digests, which is maximally distinctive material. Real
arguments are natural language and URLs, and they share structure: common words, the same domain,
the same path prefix, the same parameter names. Two concurrent calls to one API share far more than
two random fragments do, so the matched fragment will frequently be present in several in-flight
calls at once, which is `CONTENT_AMBIGUOUS` by definition.

Measurable form: per rung N, the **discrimination ratio** `CONTENT_UNIQUE / (CONTENT_UNIQUE +
CONTENT_AMBIGUOUS)`. On the bench this ratio was 1.0 in the `all_distinct` cell at N = 2, 5 and 10.
B1 predicts it is below 1.0 here, and that it falls as N grows.

What falsifies B1: a discrimination ratio at or near 1.0 at N = 5 or N = 10. If that happens, the
prediction was wrong and the written prediction is in front of the result, which is the point of
writing it.

What CANNOT falsify the second half of B1, stated because the asymmetry is easy to miss: whether a
`CONTENT_UNIQUE` claim made here was CORRECT is not checkable in this pass at all. There is no
ground truth, so "the failure mode is ambiguity rather than a false claim" is testable only in the
weak sense that ambiguity is the dominant non-unique outcome among matched flows. A false claim
would be invisible. Phase C, where the pattern is adversarial and ours, is where that half becomes
falsifiable.

**B2. Most realistic calls will not be matchable at all, so `UNATTRIBUTED` will dominate every rung
and the grade distribution will be thin at the top rather than wrong at the top.**

Mechanism: byte-literal matching needs a 16-byte run surviving verbatim onto the wire. Realistic
arguments break that in four ordinary ways, none of them adversarial: values shorter than k (a
timezone, a one-word query), percent- and plus-encoding of spaces, structured arguments the server
reassembles into its own request shape, and arguments that never travel because the server answers
locally. Nothing about this is a defect: it is negative 3 priced in realistic material.

Measurable form: the share of flows graded `UNATTRIBUTED` in the concurrent pass, and the share of
driven calls whose arguments contain no 16-byte run at all.

What falsifies B2: content matches on the majority of flows.

Why B2 is pre-registered alongside B1: without it, a low `CONTENT_UNIQUE` count could be read as
B1 confirmed, when the cause would be that almost nothing was matchable in the first place. B1 is
about **discrimination among candidates**; B2 is about **how many flows ever reach the question**.
They are separate claims and the run answers them separately.

<!-- PREREGISTERED:END -->

### Observed, concurrent pass

Not yet run. This section is filled from the committed artifact and nothing else, and the
prediction block above is not edited when it is.

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

### Sensor gate (phase A): the measured result

Built and run 2026-09-18. 19 waves, 82 calls, 85 outbound connections, at concurrency levels
N = 1, 2, 5 and 10. Committed artifact: `docs/figures/20260918T212417Z-instrument.json`, regenerated by
`python -m mcpfanout.cli bench-verify --run runs/20260918T212417Z`.

| Criterion | Threshold | Measured |
| --- | --- | --- |
| Capture recall | >= 95% | **1.0** (85 of 85) |
| False strong attributions | zero | **0** (33 strong, all correct) |
| False provenance matches | < 1% | **0.0** (0 of 17 flows that carried nothing) |
| Normalized result reproducible | required | **yes**, two runs identical on the normalized block |

Every discrimination cell produced the grade it predicted, and the predictions were written
before the run:

| Cell | Predicted | Observed |
| --- | --- | --- |
| `all_distinct` (N = 2, 5, 10) | `CONTENT_UNIQUE` | 17 of 17 |
| `all_shared` (N = 2, 5, 10) | `CONTENT_AMBIGUOUS` | 17 of 17 |
| `two_shared_rest_distinct` (N = 5, 10) | mixture | 11 `CONTENT_UNIQUE`, 4 `CONTENT_AMBIGUOUS`, zero wrong pairings |
| `no_arguments` (N = 2, 5, 10) | `UNATTRIBUTED` | 17 of 17 |
| `target_channel` (N = 5) | `CONTENT_UNIQUE` | 5 of 5 |
| `header_channel` (N = 5) | `UNATTRIBUTED` (known negative) | 5 of 5 |
| `late_egress` | `UNATTRIBUTED` | 1 of 1 |
| re-encoded (base64, gzip, JSON-escaped) | no content match | 3 of 3 missed |

**So content matching does discriminate between concurrent calls**, at N up to 10, with zero
false strong attributions. That is the phase A answer and the precondition gate rule 8 required.
It is not the phase B answer: it says the instrument works, not that real servers behave in a way
that makes the instrument useful.

**Known negatives, sized rather than described.** 8 of 85 connections carried material in a
channel byte-literal matching cannot read (a request header, or a re-encoded body). The sensor
attributed none of them, which is the correct outcome and the figure for what negative 3 costs.

**What this run does NOT establish**, each stated because the number above invites the opposite
reading:

- **The bench is not a real server.** It was written to be measurable. A real server can egress
  in ways nobody designed a cell for, and phase B is where that shows.
- **HTTP only.** The sink speaks plain HTTP, so a capture defect specific to TLS termination
  would pass here and appear in phase B. Attribution and recall are both observable on a request
  line and a body, which is why the trade was taken.
- **One destination per call.** That is the comparator's join key, and it makes this run useless
  for number 2: distinct domains per call is 1 by construction.
- **The first bench run failed, and on the bench rather than on the sensor.** Every
  `all_distinct` flow came out `CONTENT_AMBIGUOUS`, and the sensor was right each time: the
  fragments shared a constant 24-byte tail, over k = 16, so k-grams from the tail were in every
  call's argument digests and every flow matched every call. A bench whose fragments collide
  measures its own collisions. `tests/test_bench_metrics.py` now fails if any two fragments in a
  discriminating wave share a k-gram, because that is a precondition of the experiment and not a
  detail.

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
