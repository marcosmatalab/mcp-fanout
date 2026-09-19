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
information-disjoint calls produce a content match that implicates the wrong call, at the shipped
k and with no weighting. In the grade vocabulary that is not a false `CONTENT_UNIQUE`: an extra
implicated candidate turns what should be `CONTENT_UNIQUE` into `CONTENT_AMBIGUOUS`, which is the
safe direction and is exactly what prediction B1 in `docs/PHASES.md` says will dominate. It becomes
a false `CONTENT_UNIQUE` only when the true cause's own material does not reach the wire while a
bystander's does, which the `search_query` family shows is not hypothetical: there, encoding
suppresses the true match and any surviving bystander run would win uncontested.

## F1.2: the k sweep

Pending. `k = 16` was chosen by judgement, not by data. The sweep runs 8 to 64, minimising false
positives on the calibration half without sinking the phase A bench's content-match recall, which
remains the truth pattern. The curve and the chosen constant, with the curve cited beside it in
code, are the acceptance criteria.

## F1.3: rarity weighting

Pending. Sixteen bytes of `{"query": "` appear in every call of an API and are worth nothing;
sixteen bytes of a token are worth everything. Today they weigh the same, which is what the
`json_post` row above measures. Weighting each k-gram by its frequency in a background corpus and
requiring a minimum rarity mass before affirming a match is frequency counting, not semantics, so
it does not touch negative 3 (`docs/DOCTRINE.md`): counting how often a byte sequence occurs is a
fact about occurrence.

The acceptance criterion is a number, not a story: the F1.1 rate is re-measured with weighting on
and **must fall**. If it does not, the weighting is reverted and why it failed is written here.

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
