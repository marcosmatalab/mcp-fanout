# Calibrating the matcher before measuring volume

**This blocks phase B.** Not as advice: as gate rule 9 (`docs/THE-GATE.md`).

## Why

Phase A measured zero false strong attributions over 33 strong claims, and that figure is sound
for what it covers. What it covers is fragments that were **keyed digests**: forty bytes of
material that exists nowhere else, chosen so that a shared 16-byte run would be a hash collision
rather than a property of the language. It is the most favourable input this matcher will ever
receive.

Phase B presents the opposite. Real tool-call arguments are natural language and URLs, and calls
issued by one agent against one API share structure by nature: the same JSON envelope, the same
path prefix, the same host, the same ordinary English words. Nothing about the phase A result
bounds the error on that material. Measuring volume with an uncalibrated matcher multiplies noise
instead of reducing it, and until there is a number here, "the error margin is tiny" is an
adjective.

So F1 produces the number, in three pieces, each with its own command.

## The false positive, defined exactly

Two calls, A and B, in flight at the same time, sharing **no information**. A's request goes out.
The matcher asks, per in-flight call, whether a k-gram of that call's arguments appears in the
request; that per-call question is exactly what separates `CONTENT_UNIQUE` from
`CONTENT_AMBIGUOUS` in `capture_addon`. If the answer is yes for B, the matcher has implicated a
call that did not cause the transfer.

That is a false positive, and it counts the same whether the shared bytes came from a JSON key or
from the word "the". In both cases the evidence points at a call that had nothing to do with the
request, which is the only thing attribution is supposed to get right.

## The corpus, and the two halves

`corpus/negative/calibration.json` and `corpus/negative/held-out.json`. Four families, 32 calls
per half, **224 ordered pairs per half**. Ordered, because "B's arguments in A's request" and "A's
arguments in B's request" are different events and both happen. Within a family only: pairs drawn
across families share nothing but the alphabet, so counting them would deflate the rate with cases
nobody finds hard.

| Family | The shape | Why it is in the corpus |
| --- | --- | --- |
| `search_query` | `{query}` in, `GET /api/search?q=<plus-encoded>` out | free text, the most common thing an agent sends, and the case where shared English carries the most bytes |
| `rest_path` | `{owner, repo, path}` in, `GET /repos/<owner>/<repo>/contents/<path>` out | structured arguments reassembled into a path. Included because it is expected to behave BETTER: a corpus of only hard shapes would overstate the rate |
| `doc_url` | `{url}` in, that URL's path out | sibling documents on one site, so the shared run is a taxonomy prefix plus however many leaf characters happen to agree |
| `json_post` | `{text, locale}` in, a JSON body echoing both out | the worst case and the most ordinary one: the envelope and the enum travel verbatim |

**Every family declares the literal byte runs its calls share, and every call declares the values
that carry its information.** Both are checked (`tests/test_negative_corpus.py`): a declared shared
literal must appear in every call of its family, and no declared information value may appear
anywhere in another call of the same family. Without the first the corpus would be unrelated
strings and the rate would flatter the matcher; without the second a match would be a true positive
counted as a false one.

**The request shapes are re-derived from the arguments in the test suite.** They are data, so they
could say anything, and a false-positive rate measured against a wire format nobody sends would be
a number about our imagination.

### The holdout, enforced in code

All three F1 pieces are measured against this one corpus, so the failure to design against is
obvious: tune the matcher until the corpus is happy, then publish the corpus's verdict on the
matcher. Hence:

- **the calibration half** is for tuning: choosing k, choosing a threshold, trying something out;
- **the held-out half** is measured once, at the end, and is what gets published;
- `calibrate.load_negative` **raises** `HeldOutViolation` when the held-out half is asked for with
  a calibration purpose, and the CLI derives the purpose from the half so the choice is not a flag
  somebody in a hurry can flip;
- the reserved filename appears in exactly one place in `src/`, the loader's own table, and a test
  fails if any other module names it;
- a test fails if the two halves stop being independent, in either direction, over the whole byte
  content of every call and not merely over ids.

## F1.1: the measured rate

Command: `make fp` (held-out, published) and `make fp-calibration` (the one to look at while
working). Artifact: `docs/figures/calibration/fp-held-out-k16-unweighted.json`, which is what the
figures below are read from, so the prose cannot drift from the measurement
(`tests/test_calibration_figures.py`).

**Held-out half, k = 16, no weighting: 66 false positives in 224 pairs, a rate of 0.2946, Wilson
95% interval [0.2388, 0.3574].**

This is the **baseline at the k that was chosen by judgement**, kept as the measurement F1.1 was
asked for and as the before half of the comparison F1.2 makes. The figure at the k the sweep chose
is in the F1.2 section below, and it is not this one.

| Family | Pairs | False positives | Rate | Wilson 95% |
| --- | --- | --- | --- | --- |
| `search_query` | 56 | 0 | 0.0 | [0.0, 0.0642] |
| `rest_path` | 56 | 0 | 0.0 | [0.0, 0.0642] |
| `doc_url` | 56 | 10 | 0.1786 | [0.1, 0.2984] |
| `json_post` | 56 | 56 | 1.0 | [0.9358, 1.0] |

**The pooled rate is the least interesting number in that table.** The spread is the result, and it
says something a single figure cannot:

- **`json_post` fails every single pair.** The server's body repeats the argument envelope, so
  `"locale": "en-US"` and `"text": "` are on the wire verbatim in every request, and a 16-byte run
  of shared field structure exists in every pair before a word of the payload is compared. Nothing
  about the payloads matters. This is the case F1.3 exists for.
- **`search_query` fails none, and the reason is an accident rather than a strength.** The
  arguments carry spaces and the query string carries `+`, so the long shared run
  `{"query": "how to ` never reaches the wire in that form. The same encoding that makes threat 11
  a false-negative problem is what suppresses the false positives here. A server that passed the
  query through unencoded, or encoded it as `%20`, would move this family toward `json_post`, and
  nothing in the matcher would notice.
- **`rest_path` fails none for a real reason.** The JSON envelope never travels, and the path
  segments are distinct, so there is nothing 16 bytes long to collide on.
- **`doc_url` fails 10 of 56**, all of them sibling pages whose leaf names begin with the same
  letters under the same section prefix. This is the family whose rate should move most with k.

**What the number means for phase B.** Roughly three in ten concurrent pairs of realistic,
information-disjoint calls produce a content match that implicates the wrong call, at k = 16 and
with no weighting. (At the k the sweep chose it is zero on this corpus; the reasoning below is what
that k had to fix.) In the grade vocabulary that is not a false `CONTENT_UNIQUE`: an extra
implicated candidate turns what should be `CONTENT_UNIQUE` into `CONTENT_AMBIGUOUS`, which is the
safe direction and is exactly what prediction B1 in `docs/PHASES.md` says will dominate. It becomes
a false `CONTENT_UNIQUE` only when the true cause's own material does not reach the wire while a
bystander's does, which the `search_query` family shows is not hypothetical: there, encoding
suppresses the true match and any surviving bystander run would win uncontested.

## F1.2: the k sweep

`k = 16` was chosen by judgement. It is now chosen by a curve. Command: `make ksweep`. Artifact:
`docs/figures/calibration/ksweep-calibration.json`, which holds every integer k from 8 to 64; the
rows below are the ones where something changes.

**Three curves, and each one alone picks a different k.** That is why they are read together:

- **false positives**, on the calibration half. Falls as k grows. Alone it picks the largest k.
- **bench detection recall**, over the 60 phase A transfers the bench designed to be detectable.
  The truth pattern F1.2 was told to protect. Alone it picks the smallest k.
- **self-match recall**, on the negative corpus itself: can the matcher still find a call's own
  arguments in that call's own request? The same question as bench recall, asked of natural language
  and URLs instead of keyed digests. It is here because the bench's fragments are 40 bytes **by
  design**, so "recall survives a large k" is a fact about the bench and not about real material.

| k | false positives | bench recall | self-match on realistic material |
| --- | --- | --- | --- |
| 8 | 0.5 | 1.0 | 0.9375 |
| 10 | 0.2946 | 1.0 | 0.8125 |
| 16 | 0.2768 | 1.0 | 0.5312 |
| 18 | 0.25 | 1.0 | 0.5 |
| 22 | 0.0 | 1.0 | 0.5 |
| 24 | 0.0 | 1.0 | 0.4375 |
| 32 | 0.0 | 1.0 | 0.25 |
| 40 | 0.0 | 1.0 | 0.25 |
| 41 | 0.0 | 0.9167 | 0.25 |
| 48 | 0.0 | 0.0 | 0.25 |

**The rule, written in code before the numbers were looked at** (`calibrate.choose_k`): keep the k
values at the best observed bench recall, take the lowest false-positive rate among them, break the
tie toward the **smallest** k, because every byte of k is a false negative on some real fragment
shorter than it. A k at which a known negative became "detectable" is disqualified outright,
whatever its rate: that would be a collision counted as a success. None was, at any k in the range.

**It picks k = 22.** The first k at which the structural collisions disappear entirely, with phase A
recall intact. Nineteen values (22 to 40) share that rate and that recall; the tie breaks downward.

**The holdout agrees, which is the point of having reserved it.** k was chosen against the
calibration half alone. Measured once on the reserved half at the chosen k:
**0 false positives in 224 pairs, a rate of
0.0, Wilson 95% [0.0, 0.0169]** (artifact
`fp-held-out-k22-unweighted.json`). Every family, including the one that failed 56 of 56 pairs at
k = 16, is now at zero. The upper bound is what to quote, not the zero: 224 pairs cannot distinguish
"never" from "under two per cent".

**What it cost, priced rather than waved at.** Self-match recall on realistic material moves from
0.5312 at k = 16 to 0.5 at k = 22, so three per cent of the true matches this corpus can express are
gone. A concrete instance, small enough to read, is in the selftest fixture: at k = 16 a flow matched
55 bytes of context, the 36-byte synthetic secret plus a 19-byte `DB_PASSWORD=` line; at k = 22 that
line is shorter than one k-gram and contributes nothing, so the figure is 36
(`tests/test_aggregate.py`). **Every false negative pushes the published attributable share down**,
which is the safe direction, and it is the direction this trade deliberately buys.

**Read the bench column last.** It holds at 1.0 to k = 40 and collapses at 41, which is the length
of the bench's fragments plus its two-byte prefix. That cliff is evidence the sweep can see recall
fall; it is not evidence that a large k is safe. The self-match column is, and it says the opposite:
from 0.9375 at k = 8 to 0.25 at k = 32, real material stops being matchable long before the bench's
does. `tests/test_bench_metrics.py` now pins the fragment length between k + 8 and the top of the
sweep range, so the bench cannot drift into hiding that cliff.

**Three copies of k became one.** The constant lived in `shingle.py`, in `registry/servers.yaml` and
as a literal in `harness/run.sh`, and the capture addon carried a fourth as an environment default.
Moving the constant exposed all of them: the addon kept matching at 16 while everything else moved,
which does not error, it just silently stops matching, and a capture would have graded at a k no
published figure describes. `run.sh` now reads the constant, the addon defaults to it, and a test
pins the registry to it.

## The self-match ceiling. The number that bounds everything phase B publishes

Command: `make inventory`. Artifact: `docs/figures/calibration/inventory-k22.json`.

This figure was a column in the k sweep's table and it does not belong there. The delta across k is
irrelevant (0.5312 at k = 16, 0.5 at k = 22); **the level is what
matters, and it was already the level at k = 16**: half of the realistic material does not match
itself.

### What self-match means, exactly

For one call, take the bytes the matcher indexes on the cause side, which is
`driver.args_bytes(its arguments)`, the same serialisation the driver publishes to the capture
addon. Take the bytes of the request that **that same call** caused, its declared target and body.
Ask the shipped matcher whether any k-gram of the first appears in the second.

It is the true-positive question in the easiest form it has: the call is its own cause, there is no
competing candidate, nothing is concurrent, and no window is involved. **A call that fails here can
never be attributed by content anywhere**, under any concurrency, by any grade.

Measured over `corpus/negative/calibration.json`, the calibration half of the negative corpus: 32 calls in four
families, the same material the false-positive rate is measured over. It is **not** recall against
real servers: the requests are the corpus's declared ones, re-derived from the arguments in the test
suite, so this measures realistic argument SHAPES rather than the wire behaviour of ten real servers.

### Why it is 0.5, decomposed

Two thresholds, and they are different guarantees. A run of at least **k = 22** bytes IS
found, because numbers 4 and 5 match exact k-grams. A run of at least **w + k - 1 =
29** bytes is *also* guaranteed to survive winnowing, which is what
the persisted digest-only fingerprints use. Between the two, a match enters the numbers but may not
be reconstructible later from what was kept on disk.

| Family | Calls | Self-match | Longest shared run, min / median / max | At or above 29 / between 22 and 28 / below 22 |
| --- | --- | --- | --- | --- |
| `json_post` | 8 | 1.0 | 68 / 69 / 72 | 8 / 0 / 0 |
| `doc_url` | 8 | 1.0 | 23 / 27 / 31 | 3 / 5 / 0 |
| `rest_path` | 8 | 0.0 | 14 / 15 / 16 | 0 / 0 / 8 |
| `search_query` | 8 | 0.0 | 7 / 8 / 13 | 0 / 0 / 8 |

**Two of the four families are structurally invisible, and for two different reasons.** In
`rest_path` the JSON envelope never reaches the wire: the server reassembles the fields into a path,
so the longest run the arguments share with the request is a single path segment of 14 to 16 bytes.
In `search_query` the arguments carry spaces and the query string carries `+`, so the run breaks at
the first space and the longest survivor is 7 to 13 bytes. Neither is a defect in the matcher and
neither is fixable without inferring, which is negative 3.

**The planted bait is not the problem.** All
5 of the `CANARY_` values in
`corpus/context/` sit at or above the winnowing floor, which the k + 8 rule in
`tests/test_corpus_matches_probes.py` enforces. The ceiling is about the ordinary argument material
an agent sends, not about the markers we plant in it.

**One caveat nobody had written down.** 5 of the 8
`doc_url` calls share a run between 22 and 28 bytes.
Those matches enter numbers 4 and 5 but are **not** guaranteed to be present in the winnowed
fingerprints that get persisted, so a later audit of the stored digests may not be able to
reconstruct a match the run reported. The numbers are computed from exact k-grams, so they are
correct; what is bounded is the after-the-fact auditability.

**The phase A contrast, which is the point of having a bench at all.** All 60 detectable bench
transfers share a run of 40 to
45 bytes, every one above both
floors. The bench's material is keyed digests, so it self-matches perfectly, and that is exactly why
its recall figure says nothing about real arguments.

### What follows: number 5 is published as a lower bound

**An attributable share measured by a sensor that cannot see half of the realistic material it is
shown is at most half of the true share. Number 5 is therefore published as a LOWER BOUND, not as an
estimate, and this figure is the reason.** The same sentence is in `docs/THREATS.md` and in
`docs/THE-SIX-NUMBERS.md`, and `number_5`'s own output carries it as `published_as`, so the figure
cannot be quoted without it.

This is a limit to declare, not a defect to fix before phase B. Every cause of it pushes the
published share **down**: a miss is a false negative, which is the safe direction. What would be
unacceptable is publishing the share as though the sensor saw everything.

## F1.3: rarity weighting. Measured, and REVERTED

Command: `make rarity` (exit 0 if the rate fell, 1 if it did not, so the verdict is the exit code
and not a reading of this prose). Artifact:
`docs/figures/calibration/rarity-acceptance-k22.json`. Implementation: `src/mcpfanout/rarity.py`,
which is **not in the matching path** and is not imported by `match.py` or by the capture addon.

The idea is sound and was worth measuring. Twenty-two bytes of `{"locale": "en-US", ` appear in
every call of an API and are worth nothing; twenty-two bytes of a token are worth everything. Today
they weigh the same, which is exactly what the `json_post` row of the F1.1 table measures. Weighting
each k-gram by its document frequency in a background corpus and requiring a minimum **rarity mass**
before affirming a match is frequency counting, not semantics, so it does not touch negative 3
(`docs/DOCTRINE.md`): how many documents a byte sequence occurs in is a fact about occurrence.

**The acceptance criterion was a number, and the number says no.** On the reserved half at the
shipped k = 22: unweighted 0 of 224,
weighted 0 of 224. It did not fall, so **the weighting is
reverted**: the matcher ships without it.

### Why it did not fall, in three measurements rather than an excuse

**1. At the shipped k there was nothing left to remove.** F1.2 took the false-positive rate on this
corpus to zero. No mechanism lowers zero, and reporting only that would let "it did not help" hide
"there was nothing to help with". So the mechanism was probed at k = 16, where false
positives still exist: reserved half 0.2946 unweighted against
0.2946 weighted, calibration half
0.2768 against 0.2589. Four of
sixty-two removed on the half it was allowed to see, none at all on the half that counts.

**2. The background corpus cannot see that an API envelope is boilerplate.** Of the
356 colliding k-gram instances at the probe k, **180
appear in zero background documents and 176 appear in
exactly one**, out of 32. Nothing collides on a k-gram this background
considers common, because with thirty-two found documents almost nothing IS common. Every colliding
k-gram therefore carries a weight of 1.0 or 0.5, and a threshold of one unseen k-gram is met by any
of them. That is a property of the background, not a refutation of the technique.

**3. A threshold that does work is thresholding length, not rarity.** False positives match between
1 and 7
k-grams (median 6); the phase A true matches match
25 to 30. With every weight at 1.0 or
0.5, requiring more mass is requiring more matched k-grams, which is requiring a longer shared run.
It works, and it costs more than the k choice does:

| minimum rarity mass | false positives (k = 16) | self-match recall | bench recall |
| --- | --- | --- | --- |
| 1.0 | 0.2589 | 0.5 | 1.0 |
| 2.0 | 0.25 | 0.5 | 1.0 |
| 4.0 | 0.25 | 0.4688 | 1.0 |
| 5.0 | 0.0536 | 0.4062 | 1.0 |
| 6.0 | 0.0 | 0.375 | 1.0 |
| 8.0 | 0.0 | 0.2812 | 1.0 |
| 16.0 | 0.0 | 0.25 | 1.0 |

The cheapest threshold that clears every false positive is
6.0, and self-match recall on realistic material
there is 0.375. **The k the sweep chose reaches the same zero with
0.5.** Same false positives, better recall,
one parameter instead of two. The k choice strictly dominates, which is the whole argument for
reverting rather than a preference about complexity.

### What would make it necessary again

The condition is specific and worth writing down, because this result does not generalise to every
API. Weighting becomes the only available answer when a collision is **both** long and common: a
shared envelope longer than k, so a length threshold cannot separate it from a true match, and
frequent enough in a real background corpus that its weight collapses. A body that echoes a
forty-byte constant preamble in front of every payload is exactly that shape, and nothing in this
corpus has it.

Two honest limits on this verdict:

- **The technique is not refuted, our test of it is bounded.** A background of thirty-two found
  documents is a coarse proxy for "common in the world". A deployment building this index from its
  own traffic, where an envelope appears in ten thousand requests, would be testing something this
  measurement cannot reach.
- **The background is not independent of its author.** The same person wrote the negative corpus and
  chose the background sources (`corpus/background/README.md` says what they are and why the
  calibration half is among them while the reserved half may never be). A background built from real
  traffic is the genuinely independent test.

The mechanism, the measurement and the verdict all stay in the repository: the code in
`rarity.py`, the figure under `docs/figures/calibration/`, and this section. What does not stay is
the weighting switched on. A test fails if `match.py` or the capture addon ever import it while this
verdict reads `reverted`.

## Threats to this measurement

1. **The corpus is hand-authored, so the interval covers sampling variance only.** These 224 pairs
   are not drawn at random from any population of real agent traffic, and no interval can fix that.
   What can be said is what the corpus contains and why, which is the table above; what cannot be
   said is that 0.2946 is the rate an arbitrary deployment would see.
2. **The request shapes are a model of a server, not an observation of one.** They are declared per
   call and re-derived in tests from the arguments, which keeps them consistent and plausible, but
   a real server may encode, reorder, wrap or split in ways no family here reproduces. Every such
   difference moves the rate, in either direction.
3. **Within-family pairing is a choice that raises the rate.** It is the honest choice, because
   concurrent calls from one agent to one API are the case that matters, but a reader comparing this
   number with one computed over arbitrary pairs is comparing two different quantities.
4. **Four families are not the space of API shapes.** Header-carried arguments, form encoding,
   protobuf and GraphQL are all absent. The families were chosen to span "the envelope travels" and
   "the envelope does not", which is the axis the matcher actually responds to.
5. **The rate is a property of the matcher AND of k.** Quoting it without k is meaningless, which is
   why every artifact filename carries the k it was measured at.
