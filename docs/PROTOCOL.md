# The protocol: the gate, the phases, and when to stop

One document for the apparatus of government, because a reader following a rule was previously sent
between three (`THE-GATE.md`, `PHASES.md`, `STOP-CRITERIA.md`) and the rules refer to each other on
almost every line. The gate says what a run must satisfy before a number from it is reported; the
phases say in what order things may be measured; the stop criteria say when the question is
answered. Nothing here is advice. Every item is a condition, and most of them have a command.

## Part 1: the gate

Ten conditions a run must pass before any number from it is reported.

1. **Reproducible, at two levels.** The levels differ because the things being reproduced differ,
   and one standard for both produced a rule that failed for the wrong reason.

   **Level 1, byte for byte: the measurement core and every normalized artifact.** Two runs over
   the same input produce byte-identical output. Proved by `make verify`
   (`tests/test_reproducibility.py`), by `make figures-check` for the calibration figures, and by
   `make reproduce` plus `tests/test_example_runs.py` for the committed example runs.

   **Level 2, normalized result: a capture.** Two captures of the same pinned servers must agree
   on the NORMALIZED result: the same destination categories, the same logical graph, the same
   provenance sources, the same distribution of attribution grades. They must NOT be expected to
   agree byte for byte. Timestamps, traceparents, nonces, socket order and DNS answers all differ
   between captures, so a byte-for-byte rule over a capture fails on clerical noise while saying
   nothing about whether the phenomenon reproduced, which trains everyone to ignore it.

2. **A command behind every number.** Each of the six has a `make` target and an `aggregate`
   subcommand (doctrine rule 6). A figure with no command does not ship. This covers prose and
   pictures: `make claims-check` compares the README's table against the committed artifacts, and
   both SVGs under `docs/figures/` are generated from the same commands that publish the JSON.

3. **No names in aggregate output.** No server id, host or tool name in anything published. Counts,
   ratios and category breakdowns only. Enforced by
   `tests/test_aggregate.py::test_aggregate_output_leaks_no_server_names`, and by
   `tests/test_example_runs.py` for the two runs that are committed.

4. **No content stored, and no CAPTURED run committed.** Only salted digests and references. Raw
   payloads exist in memory during the hashing pass and nowhere else (`src/mcpfanout/redact.py`).

   Two things may be committed, and both are derived artifacts rather than runs. The **normalized
   aggregate** of a capture, under `docs/figures/`: counts and ratios with no hostname, no server
   id, no tool name and no digest. And two **redacted runs**, under `runs/example-*`, where every
   server id, tool name, destination and address has been replaced by a stable label and every
   digest kept (`tools/redact_run.py`, `runs/README.md`). The second is an exception written down
   rather than a rule quietly relaxed: it exists because `make n1` failed in a clean clone, and it
   carries its own cost, which is that a run whose hostnames are gone cannot be re-classified
   against a newer registry. The cost is reported in the output, not absorbed.

   **A committed artifact is never hand-edited, not even to repair a renamed path.** These three
   documents were merged into this one and every reference in the repository was updated, with two
   deliberate exceptions. The aggregates under `docs/figures/` carry the document name as it stood
   when the run was taken, because an artifact records what the code said and is not a page that
   tracks the tree; `make figures-check` fails on any edit to one. And
   `registry/package-infrastructure.json` still points at a merged document inside a comment,
   because its sha256 is quoted in every published figure that excluded a host with it: correcting
   the sentence would move the digest and make the figures describe a list that no longer exists.
   A stale pointer inside a frozen artifact is the cheaper error, and naming it here is what keeps
   it from being read as an oversight.

5. **Nothing runs outside the container, and lab accounts only.** The harness runs in Docker with a
   throwaway network, enforced by a check in `harness/run.sh` rather than by a comment.

   "No credentials at all" was the previous rule and the probe sweep measured why it does not work:
   `brave-search` exits before the JSON-RPC handshake without `BRAVE_API_KEY`, so there is no
   failed call to observe and no connection attempt to watch. The rule produced zero data for the
   servers it was meant to cover, and it implied a safety it did not deliver, since what matters is
   not the absence of a token but the blast radius of the one used. So: **lab accounts**, with
   every one of these properties, and a server is not measured until they all hold.

   - a fictitious organization, not a real one with a test project inside it
   - synthetic data only, and zero personal data of any kind
   - minimum permissions: read-only wherever the API offers it
   - revocable tokens, held outside the repository and outside the image
   - a spending limit set on the account before the first run
   - rotated at the end of the measurement, whether or not anything looked wrong

   Bait tokens in `corpus/context/` stay synthetic and unique (`CANARY_*`) and are never real
   secrets.

6. **Threats to validity written, at least four.** See `docs/THREATS.md`. A measurement that does
   not state how it could be wrong is not a measurement.

7. **Responsible disclosure, with a command behind it.** If a server egresses to a destination its
   documentation does not declare, stop and flag it. Publish nothing that locates that server until
   the finding is authorized. Aggregate first, name never (rule 3).

   `make disclosure` (`src/mcpfanout/disclosure.py`) reduces a run's destinations to the ones
   nobody expected, per server, against `registry/declared-destinations.json`, and exits non-zero
   if anything needs reviewing. Until it existed the rule was honoured by reading a hostname list
   and remembering what belongs there, which works for one server and fails for ten, silently, in
   the direction of publishing.

   **What the command does not do**, because the bound matters more than the convenience: it does
   not decide the rule. The declared set comes from the committed tool schemas and the packages'
   stated purpose, NOT from a reading of each upstream README, and the registry file says so in its
   own `_what_basis_means` field. Asserting what a document says without having read it is the
   plausible guess this project keeps finding in its own history. The command narrows a hostname
   dump to a short list to read documentation ABOUT; a person then reads it. Three outcomes, never
   two: clear, review required, and **undeterminable** when the declaration is missing, because
   unevaluated is not the same as satisfied. Its report names servers and hosts, so it stays in the
   run directory.

   **The decision procedure, in three branches.** The rule used to say "if a server egresses
   somewhere its documentation does not declare", and that sentence does not decide the commonest
   case, which is a package manager downloading a dependency.

   1. **Contacted by the launcher before the server process starts.** Not the server's egress:
      recorded apart, no disclosure. Mechanically, all three of: the flow was seen in a
      pre-first-call phase (`record.PHASES_NOT_CALL_CAUSED`), the launch command is a package
      launcher (`disclosure.PACKAGE_LAUNCHERS`), and the destination is on the declared list in
      `registry/package-infrastructure.json`. Each from declared data, none inferred from how a
      hostname looks.
   2. **A direct consequence of a corpus call, to a destination the documentation names.** Declared
      behaviour. Published as such, no disclosure.
   3. **Anything else.** Gate rule 7 fires: stop, and say so before publishing anything from that
      run. This includes pre-first-call egress that is not a package registry, which is a launched
      process reaching somewhere on its own at startup.

8. **The instrument passes before the phenomenon is measured.** No figure from a real-server run
   (phase B) may be published until the controlled bench (phase A) has passed the sensor gate in
   part 2: capture recall at or above 95%, zero false strong attributions, false provenance matches
   under 1%, and a reproducible normalized result.

   A gate and not advice, because the failure it prevents is silent. Recall and precision cannot be
   computed against a third-party server at all: recall needs a denominator of transfers we caused
   on purpose, precision needs a known cause to check against. A phase B run therefore cannot tell
   you whether the sensor worked, so measuring the phenomenon first means finding out afterwards,
   if ever, and every figure published in between is unfalsifiable.

9. **The matcher is calibrated on real language before volume is measured.** No figure from a
   real-server run may be published until the matcher's false-positive rate on structured language
   has been measured and published, with its interval, over at least 200 concurrent call pairs that
   share language structure and no information. See `docs/CALIBRATION.md`; the command is `make fp`.

   Why this is separate from rule 8, when both are about the instrument: rule 8 asks whether the
   sensor SEES what it should and CLAIMS only what it can support, and it was satisfied against
   keyed digests, the most favourable input the matcher will ever get. Rule 9 asks what those
   fragments cannot: on natural language and URLs that share a JSON envelope, a path prefix, a host
   and ordinary English words, how often does the matcher affirm a coincidence that does not exist?
   Without that figure the error bar on every volume number is unknown in the one direction that
   inflates it, and "the margin is tiny" is an adjective.

   The rule includes its own anti-tuning clause, because the corpus that produces the number is
   also the corpus any improvement is developed against. The corpus is split in two halves before
   any measurement exists: one for calibration, one reserved and measured once at the end, which is
   the half the published figure comes from. `calibrate.load_negative` refuses the reserved half to
   a calibration purpose, and tests fail if that refusal is bypassed.

10. **Every instrument needs a test that fails when the instrument is ABSENT, not only when it is
    wrong.** No figure from an instrument may be published until a test exists that goes red if
    that instrument silently does nothing.

    This is a gate rather than a style note because it is the failure mode this repository keeps
    producing, and because of what it does to the process: a wrong number gets investigated, and
    **a green gets published**. An absent instrument produces a clean run, a passing suite and an
    empty result that reads as a finding.

    **The class is established by seven instances, not argued from one.**

    - `capture_addon.py` used a relative import. mitmproxy loads an addon by path under a synthetic
      package name, so the import raised, mitmdump logged it and carried on proxying. The run
      completed, the suite was green, and `flows.jsonl` was empty, which reads exactly like a
      server that egressed nothing. Guarded by `tests/test_capture_addon_loads.py`, which loads the
      file the way mitmproxy does.
    - The addon carried its own `k = 16` after `calibrate.choose_k` moved the shipped constant to
      22. A k mismatch does not error. It stops matching, so the capture graded at a k no published
      figure describes and nothing went red.
    - `make selftest` serialised the structural fields and never populated one of them, because its
      synthetic path does not run the addon's request hook. A passing selftest was fully consistent
      with a capture layer that never called the structural matcher at all.
    - `make figures` wrote `content_denominator: null` into every committed artifact, because
      `compute_all` was called without the constant-path list. The published artifact omitted the
      quantity the published verdict is measured against, and it validated, diffed and committed
      cleanly.
    - `pyproject.toml` and `mcpfanout.__version__` said `0.1.0` while `CITATION.cff` said `1.0.0`,
      in the same commit. Two artifacts of one repository asserting different facts, each
      well-formed. Guarded by `tests/test_version_is_one_number.py`.
    - Four calibration figures stopped reproducing for eight commits. The negative corpus gained a
      fifth family, nothing regenerated the artifacts, and 654 lines of difference sat under three
      documents and a module docstring that quoted them verbatim.
      `tests/test_calibration_figures.py` was green throughout, because it checks that a figure has
      the fields a figure should have and never runs the instrument that produces it. Guarded by
      `make figures-check`, which regenerates and fails on a non-empty diff.
    - `README.md` published numbers 1 and 2 from the pass that may not claim them, stating a
      maximum of 1 where the pass that may answer says 84, and stated a cost, a reproducibility
      guarantee and a version the measurements contradicted. Nothing in the suite could tell that a
      sentence of prose had stopped being true. Guarded by `make claims-check`.

    Seven instances is not an anecdote: the class is that an ABSENT input produces a WELL-FORMED
    output, and well-formed output is what gets reviewed. The last three extend it past code. A
    document is an artifact, a figure is an artifact, and an artifact that omits or contradicts the
    result it is measured against fails at the one job it has.

    **What the test has to do, since "we have tests" was true in every case above.** It must
    exercise the instrument's real entry point, with the real loader where there is one, and assert
    a POSITIVE result that only a working instrument can produce. Asserting that a field is present
    is not enough: every instance above had its fields. Asserting the SHAPE of an artifact is not
    enough either: the only check that can tell a stale figure from a current one is regenerating
    it and comparing.

    **Applied to itself.** A detector whose job is to find something must be shown to find a
    planted instance of that something, in the same run, through the same code path. A scanner that
    has silently stopped scanning reports a clean result, which is this rule's own failure mode
    turned on the rule. `tests/test_credentials_never_persisted.py` plants a canary and fails if
    its own scanner misses it, before it reports that the artifacts are clean.

## Part 2: the three phases

Phase A is the instrument. Phase B is the phenomenon. Phase C is the attack on our own method. The
order is gate rule 8, not a preference.

### Phase A: the controlled bench

Two or three MCP servers **we write ourselves**, with egress to destinations **we also own**. The
only configuration in which ground truth exists, because we caused every transfer and know what it
contained. Cases the bench generates, each because a published figure depends on the sensor
handling it: one connection per call; several per call; simultaneous connections, the only case
that can earn `CONTENT_UNIQUE`; unique arguments per call; arguments repeated across concurrent
calls, which must report `CONTENT_AMBIGUOUS` rather than guess; payload in the body, in the query
string, and in a request header, the last being a channel the matcher is still blind to and which
is measured to size the gap; a reused connection pool; retries; and a task still alive after the
response, which breaks any time window.

**Recall and precision can only be computed here**, and therefore may never be quoted from a phase
B run.

**The subset built to fail.** Part of the bench sends the same data re-encoded: base64, compressed,
JSON-escaped. The sensor misses all three, because matching is byte-literal and that is negative 3.
The subset exists to MEASURE how much is lost, not to chase it, and the loss is documented as a
permanent known negative rather than as debt. Calling it debt would imply a future version closes
it, and closing it means inferring.

#### Sensor gate (phase A). Thresholds, because an instrument has a specification.

| Criterion | Threshold |
| --- | --- |
| Capture recall against known transfers | >= 95% |
| False strong attributions | **zero. Tolerance zero, not negotiable** |
| False provenance matches | < 1% |
| Normalized result reproducible across runs | required (gate rule 1) |

These need no market baseline. An instrument that loses known traffic is broken, and one that
claims a cause it did not have is worse than broken: one false strong attribution destroys the
evidentiary claim the product rests on, so the tolerance is zero rather than small.

#### The measured result

Built and run 2026-09-18. 19 waves, 82 calls, 85 outbound connections, at N = 1, 2, 5 and 10.
Committed artifact: `docs/figures/20260918T212417Z-instrument.json`, regenerated by
`python -m mcpfanout.cli bench-verify --run runs/20260918T212417Z`.

| Criterion | Threshold | Measured |
| --- | --- | --- |
| Capture recall | >= 95% | **1.0** (85 of 85) |
| False strong attributions | zero | **0** (33 strong, all correct) |
| False provenance matches | < 1% | **0.0** (0 of 17 flows that carried nothing) |
| Normalized result reproducible | required | **yes**, two runs identical on the normalized block |

Every discrimination cell produced the grade predicted before the run: `all_distinct` 17 of 17
`CONTENT_UNIQUE`; `all_shared` 17 of 17 `CONTENT_AMBIGUOUS`; `two_shared_rest_distinct` 11 unique
and 4 ambiguous with zero wrong pairings; `no_arguments` 17 of 17 `UNATTRIBUTED`; `target_channel`
5 of 5 unique; `header_channel` 5 of 5 `UNATTRIBUTED` as a known negative; `late_egress`
`UNATTRIBUTED`; re-encoded 3 of 3 missed.

**So content matching does discriminate between concurrent calls**, at N up to 10, with zero false
strong attributions. That is the phase A answer and the precondition rule 8 required. It says the
instrument works, not that real servers behave in a way that makes it useful.

**Known negatives, sized rather than described.** 8 of 85 connections carried material in a channel
byte-literal matching cannot read. The sensor attributed none of them, which is the correct outcome
and the figure for what negative 3 costs.

**What this run does NOT establish**, each stated because the number invites the opposite reading.
The bench is not a real server: it was written to be measurable. HTTP only, so a capture defect
specific to TLS termination would pass here. One destination per call, which makes the run useless
for number 2. And the first bench run failed on the BENCH rather than on the sensor: every
`all_distinct` flow came out `CONTENT_AMBIGUOUS` because the fragments shared a constant 24-byte
tail, so every flow matched every call. A bench whose fragments collide measures its own
collisions; `tests/test_bench_metrics.py` now fails if any two fragments in a discriminating wave
share a k-gram.

### Phase B: real servers, driven TWICE

The ten pinned servers in `registry/servers.yaml`, with both corpora aligned against their real
schemas (`registry/probes/`). This phase measures the phenomenon and nothing about the instrument.

#### Why two passes and not one

One sequential pass cannot measure the thesis, and the reason is arithmetic. `CONTENT_UNIQUE`
requires `active_calls_in_window > 1` (`match.grade_attribution`), and that requirement is the
whole defence against the tautology. Driven one call at a time, every window holds one call, so the
strong-attribution fraction of a sequential run is **0.0 by construction**, whatever the servers
do. Running phase B that way would make the thesis unobservable, with a published zero that reads
like a finding.

The reverse is also true. Numbers 1 and 2 are **per invocation**. With ten calls in flight,
"connections per call" is a figure about our own wave size, and the attribution of a connection to
a call is exactly what is in question, so a per-call distribution measured under concurrency would
be circular.

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
(`record.PASSES`), in the run directory's name, in the aggregate output and in the committed
artifact's provenance. `harness/drive_all.py` refuses to drive a second pass into a run that
already holds one: merging them would average two experimental conditions into one distribution,
and no footnote undoes that arithmetic afterwards. `make claims-check` fails if the README quotes a
number from the pass that may not publish it, which is not hypothetical: it did.

**The ladder is the bench's ladder**, N = 2, 5 and 10, capped per server by `max_concurrency` with
its reason in the registry. Same rungs on purpose, so any difference measured here is a difference
in the material and not in the level.

**The corpus rule is the inverse of the bench's.** The bench requires that no two fragments share a
16-byte run. This corpus requires the opposite: arguments that look like what an agent would really
send, which means they share domains, path prefixes, parameter names and common words. Made
artificially distinct, the concurrent pass would replicate the bench on a real server and measure
something already known. `tests/test_concurrent_corpus.py` fails if the corpus is pairwise
k-gram-disjoint.

#### Observed, sequential pass

Run `20260919T115452Z-sequential`, driven 2026-09-19. Committed artifact:
`docs/figures/20260919T115452Z-sequential.json`; reproducible from `runs/example-sequential`.
Gate rule 7 reads `clear` on it after the two flagged destinations were attributed to a cause and
disclosed (`docs/THREATS.md` threat 15, `docs/DISCLOSURE-LOG.md`).

**The denominator first, because every one of the six is a ratio over it.** 26 tool calls across
the 10 pinned servers, 23 carrying arguments. **3 calls errored and the reasons are not
interchangeable**: 2 are `brave-search`, which exits before the handshake without `BRAVE_API_KEY`
(threat 8), and 1 is a `github` search that returned an authentication error over a live protocol
connection. The first is a server that never ran; the second ran and refused. 96 flows, 89 during
`driving` and 7 during `handshake`.

| Number | Measured | Read it as |
| --- | --- | --- |
| 1. Outbound connections per tool call | raw p50 **0**, p95 **3**, max **84**; excluding package infrastructure p50 **0**, p95 **2**, max **3** | the gap between the columns is one server installing a package mid-call (threat 17). 89 of the 96 flows are package infrastructure; 7 more are the launcher's, before any server process existed |
| 2. Distinct domains per tool call | p50 **0**, p95 **2**, max **3** | the median tool call in this corpus reaches nothing at all |
| 3. Servers propagating `traceparent` | **0 of 10**, and 0 in both protocol segments (3 servers answering `2024-11-05`, 7 answering `2025-11-25`) | uptake of the trace-context convention is zero here, and the segments say the answer is not an artefact of age |
| 4. Provenance coverage | context channel **0.0** (0 of 96 flows carried a planted bait fragment); argument channel **2 of 96**, both through the request target, 0 through a body | of 3494 observed outbound bytes, 2948 were request target and 546 were body |
| 5. Attribution grades | 89 `UNATTRIBUTED`, 5 `TEMPORAL_ONLY`, 2 `CONTENT_MATCH_UNCONTESTED`, **0 strong** | 0.0 strong attribution is **by construction**, not a finding: `max_active_calls_in_window` is 1 |
| 6. Self-hostable third parties | **0.0** over 4 distinct nodes, all `remote_leaf` | 4 nodes is a denominator too small to carry a fraction, and the count is published beside it for that reason |

**The finding of this pass is the shape of the zeros.** 8 of the 10 servers produced no call-caused
egress at all: six are local by design and behaved that way, `brave-search` never started, and
`github` answered its authentication failure without reaching a host we could observe. Only two
servers egressed during a call. So numbers 1, 2 and 6 rest on two servers, and threat 8 is the
sentence to read beside them.

**What this pass may NOT be quoted for**, restated because a table invites it: nothing about
whether content matching discriminates. Its 2 content matches are graded
`CONTENT_MATCH_UNCONTESTED` because exactly one call was in flight, which is the definition of this
condition rather than a result within it.

#### Pre-registered predictions for the concurrent pass

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

#### Observed, concurrent pass

Run `20260919T194649Z-concurrent`, driven 2026-09-19. Committed artifact:
`docs/figures/20260919T194649Z-concurrent.json`; reproducible from `runs/example-concurrent`. Gate
rule 7 reads `clear`. Filled from that artifact and nothing else; the prediction block above is
untouched and `tests/test_phase_b_prediction.py` would fail if it were not.

**This run supersedes two earlier concurrent runs and the difference is the point.** The two before
it were driven through a proxy blind to Node's global `fetch` (threat 19), so they described a flow
sample biased toward the servers whose clients honour `HTTP_PROXY`. They are superseded, not
retracted: each remains a correct statement about the flows that were visible when it was taken,
and the three together are the honesty curve.

**The denominator.** 130 calls across the ladder (20 at N = 2, 40 at N = 5, 70 at N = 10), 3
errored for the reasons threat 8 already names. 140 flows.

| Rung | `CONTENT_UNIQUE` | `CONTENT_AMBIGUOUS` | `UNATTRIBUTED` | Discrimination ratio |
| --- | --- | --- | --- | --- |
| N = 2 | **4** | 2 | 4 | **0.667** |
| N = 5 | **8** | 2 | 5 | **0.8** |
| N = 10 | **13** | 2 | 91 | **0.867** |
| (window 0: launcher) | | | 9 | |

Pooled: 25 `CONTENT_UNIQUE`, 6 `CONTENT_AMBIGUOUS`, 109 `UNATTRIBUTED`. Three denominators,
published together and never one alone (`docs/PREREG-F2.md` section 16): **0.1786** over all 140
flows, **0.4386** over the 57 call-caused eligible flows, and **0.6579** over the 38 that are also
content-eligible, which is the figure number 5 is read as and the one that misses the
pre-registered 0.80.

**B1's first half holds and its second half is falsified, and the prediction said in advance what
would falsify it.** It predicted a discrimination ratio below 1.0 that FALLS as N grows. The ratio
is below 1.0 at every rung, so the mechanism is real: on realistic arguments the matched fragment
is frequently present in more than one in-flight call. But it RISES with N, from 0.667 to 0.867,
which is the opposite of the predicted direction. The reason is visible in the same artifact and is
not a rescue: the two ambiguous flows per rung are a constant, not a share, so a rung with more
matched flows dilutes them. A prediction about a ratio was the wrong measurable form for a claim
about a count, and that is a defect in the prediction rather than in the result.

**B2 is confirmed.** 109 of 140 flows are `UNATTRIBUTED`, 0.779, so the grade distribution is thin
at the top rather than wrong at the top, exactly as predicted. Most of those are package
infrastructure, ineligible by construction (threat 17's server at wave scale), and 9 are the
launcher's.

**The qualifier, which is smaller than it was and still load-bearing.** The 31 structural matches
come from **three** servers, 15, 14 and 2, rather than from one as in the superseded runs. Three is
not many, and the third only became visible when the packet capture found the client the proxy
could not see. A ratio computed over three servers' flows is still a fact about those three
servers.

**What this pass may NOT be quoted for**: numbers 1 and 2. With ten calls in flight, connections
per call is a figure about our own wave size (`docs/THREATS.md` threat 13), and the artifact
carries them only because the aggregate computes all six from any run. `make claims-check` enforces
this against the README.

### Phase C: attacking attribution

Concurrent calls, deliberately adversarial: the same fragment in several simultaneous calls,
fragments split across parameters, a server that pools connections across calls, a server that
delays egress past the response.

**This is the phase that answers the project's actual question.** Whether content matching recovers
attribution where time cannot is only answerable when time cannot, which means concurrency, and
whether a strong claim was CORRECT is only answerable where the pattern is ours to design. Phase A
shows the sensor can discriminate when we wrote the material; phase C is where we did not. It is
not started, and the repository says so rather than implying the concurrent pass covered it.

## Part 3: the product gate and when to stop

### Product gate (phase B). Directional, and deliberately WITHOUT a threshold.

There is no number here on purpose. Nobody has measured MCP fan-out or content-recoverable
attribution, so there is no baseline against which to set a bar, and a bar invented to look
rigorous would kill a good project or wave through a bad one with equal confidence. No figure is
written in this section, deliberately, because a number written here as an illustration is a number
someone lifts later as a target. `tests/test_doc_references.py` fails if one appears.

What is pre-registered instead:

1. The figure is published **whole and broken down**: every distribution, every grade, every named
   reason, no single headline ratio.
2. The go/no-go decision is **argued in writing against that figure**, and the argument is
   published with it.

A written argument against a published breakdown is auditable. An arbitrary threshold is not, it
just looks like it is.

### Stop gate

Stop if any of these holds.

- **Median fan-out of 1 with zero content matching.** Servers call their own API and nothing of the
  context leaves. The idea is real and the problem is small.
- **The target market is hosted remote MCP.** The observer can only watch the egress of a process
  it hosts, so a hosted-remote market is unobservable by this method, not merely harder.
- **Buyers consider their existing gateway sufficient.** Not a technical failure. It decides the
  same thing.

### The branch that fired

**Stop, small problem.** Number 1's median is 0 and number 4 is zero bytes: the causal union is
trivial on this sample and there is no headline about fan-out. What the criterion did not
anticipate is that the instrument would fail its own pre-registered threshold on the way
(`docs/PREREG-F2.md` section 16), so "write it up and stop" is being followed with a negative
result about the apparatus rather than a small result about the phenomenon.

The alternative branch, for completeness: if the median fan-out were greater than 1, or literal
coincidence appeared with files a user would not expect to leave, there would be both a product and
a headline, and number 5 would be the viability signal for the architecture decision in
`docs/METHOD.md`.

**Stop and disclose, always.** Independent of the two above: if any server egresses to a
destination its documentation does not declare, stop the run and follow rule 7. A surprising
destination is a finding to be handled responsibly before it is a data point.

### What the measurement cost, and what it does not decide

Measured rather than estimated, because an earlier version of this paragraph guessed "one afternoon
and about 10 EUR of compute" and both figures were wrong: **0 EUR** of cloud compute, everything in
Docker on one machine; **0 EUR** of paid APIs, the only credential being a free-tier GitHub token;
**138 seconds** of actual driving across 21 capture runs; **two days** of wall clock. The money
cost is genuinely zero and the real cost is attention.

What it does not decide:

- Whether this sells on its own or is again a fine feature inside someone else's product. The
  number does not answer that, but without the number the question cannot even be posed.
- The Zscaler CTPH patent (US20210374121A1), which must be read in full before any commercial use.
- Which part of the chain runs on our own machine, which sets the ceiling on the product's value.
