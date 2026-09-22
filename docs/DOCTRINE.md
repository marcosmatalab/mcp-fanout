# Doctrine

The standing rules this repository operates under. Every design decision in the code cites one of
them: when a comment says "negative 3" or "rule 6", this is the referent. The operating rules for
an agent working here are in [`../CLAUDE.md`](../CLAUDE.md); the conditions a run must satisfy
before a number is reported are in [`PROTOCOL.md`](PROTOCOL.md). This file is the why.

## The four negatives (never)

1. **Never inject.** Nothing is planted inside a third party: no marker, no token, no code, no
   identifier smuggled into a call toward someone else's system. The observer lives at the own edge
   and watches bytes leaving the machine and bytes coming back. A marker that travels the chain
   cannot be passive and report at the same time, and planting one is an attack surface, a
   terms-of-service problem and, with customer data, a data-minimization problem.
2. **Never store content.** Only salted digests and references. The collector may see payloads that
   carry personal data, so what survives memory is a fingerprint, never a byte. The only sentence it
   can emit is: "the fragment with hash X, from reference Y, appeared in the output toward domain
   Z." Enforced in `src/mcpfanout/redact.py`.
3. **Never infer.** A literal match is auditable evidence with a measured false-positive rate.
   Paraphrase, semantic propagation and "the model probably reworded it" are inference: a different
   product with different epistemics. If a server re-encoded a value before sending, we miss it and
   say so.
4. **Never act on what is observed.** Observe and record. Do not block, redact in flight, alter or
   intervene. This is not a gateway. The whole product is evidence, not enforcement, and this is the
   negative that shapes everything: it forces the edge-observer design and forbids the marker.

## The boundary of negative 3: structure is decomposed, meaning is not

Negative 3 forbids inference. It does not forbid PARSING, and the difference needs a line rather
than a habit, because the structural matcher decomposes a URL where the k-gram matcher read bytes.

**Allowed, because it is deterministic and reversible in principle:** splitting a URL into host,
path segments and query values per RFC 3986; percent-decoding and plus-decoding those; walking a
JSON document to its scalar leaves. Each recovers a structure the sender put there, with a
published algorithm, and a second implementation of the same rule gets the same answer.

**Forbidden, because each one guesses what the sender meant:** case folding, stemming or
lemmatising, edit distance or any fuzzy comparison, synonym expansion, embeddings or any learned
representation, and tokenising prose into words.

The test of a proposed step is not whether it improves recall. It is whether two independent
implementations of the written rule must agree on every input. Percent-decoding must. Stemming need
not.

## Digests of short tokens are obfuscation, not control

Negative 2 says only salted digests survive memory. That is still true and it is no longer
sufficient on its own, because the structural matcher changed what gets digested.

A keyed digest of a 22-byte window of natural language is a fingerprint: the space of inputs is too
large to enumerate. A keyed digest of a structural token is not. `docs`, `deploy`, `warn`, `acme`,
`en-US`, a status, a ref name, a four-digit code: dictionary words and enums of three to six bytes,
which anyone holding the key recovers by enumeration in seconds. The 22-byte window had been acting
as an accidental privacy floor, and decomposing to tokens removes it.

**So: for short tokens, a keyed digest is obfuscation, not access control.** It raises the cost of a
casual read and does not bound a determined one. Anything built on it must be built as if the tokens
were recoverable by whoever holds the evidence file.

A per-installation key does not close it either, because of where the threat is: a key protects the
evidence from an outsider who obtains the file without it, and the people who read an evidence file
in the normal course of their work hold the key by construction. Both PENDING gaps in `redact.py`, a
per-installation key with rotation and a minimum-fragment-length policy, are therefore
**preconditions of deploying the structural matcher outside a measurement**, not pre-deployment
to-dos.

**The option this leaves open, recorded and not adopted.** Store the digest of the ORDERED TUPLE of
a call's structural tokens plus the token count, and never persist the individual token digests. A
tuple digest over four tokens is not enumerable the way four separate three-byte tokens are. What it
costs: containment is a SUBSET test and a tuple digest supports only an EQUALITY test, so partial
containment becomes invisible, at a recall cost nobody has measured. And it collides with threat 16,
which asks whether a match that entered the numbers can be re-derived from what was persisted: a
tuple digest makes a match LESS re-derivable, not more. Privacy and auditability pull in opposite
directions here, and the honest statement is that this repository has measured neither side.
Choosing is a decision for whoever owns a deployment, made with threat 16 open on the desk.

**The legal status of what we store, stated plainly.** A keyed hash of a personal data item is
**pseudonymised data, not anonymised data**, under recital 26 of the GDPR, and it remains within the
scope of the Regulation. This belongs in the doctrine rather than in a compliance appendix because
it changes what may be claimed: "we only store hashes" is not a statement that the regulation stops
applying.

## The evidence model: three separate claims

This replaced a single `EFECTIVO` / `DECLARADO` / `INDETERMINADO` column that asked three questions
and answered with one word. The three claims are recorded and reported separately, and **they never
appear together in one sentence**, because a sentence that joins them is the conflation returning.

| Claim | Question | Where |
| --- | --- | --- |
| Occurrence | was the transfer observed, and readable | number 4, `occurrence_counts` |
| Provenance | did the request carry recognisable material of ours | number 4, `provenance_counts` |
| Attribution | could it be tied to a tool call, and how strongly | number 5, `attribution_grades` |

An unreadable request yields provenance `unknown`, never `none`: "we looked and found nothing" and
"we could not look" are different findings, and collapsing them is how a blind spot reads as a clean
result. A context match is a leak claim; an argument match is a causal key. The six attribution
grades are listed in the README; a grade is a claim about the QUALITY OF THE EVIDENCE, never about
certainty of cause.

**The tautology this design exists to avoid.** If `CONTENT_UNIQUE` meant "the fragment matched and
nothing competed", it would be true of every match under sequential driving by construction, and the
harness would publish 100% strong attribution having discriminated nothing: a restatement of the
experimental setup wearing a measurement's clothes. So `CONTENT_UNIQUE` requires
`active_calls_in_window > 1`, a sequential run emits none, and `tests/test_evidence_model.py`
asserts that it emits none.

**Ineligibility is not correlation.** The first real capture produced 90 flows the old column called
`DECLARADO`, of which 87 were a package registry that cannot carry a tool call's arguments at all:
it asserted temporal correlation where the truth was ineligibility. Those flows are `UNATTRIBUTED`
with the reason named. Eligibility is checked **after** trace and content evidence, never before: a
package-registry flow that did carry our traceparent, or a literal fragment of a call's arguments,
is attributed on that evidence and stays visible. The declared exclusion list withholds a temporal
guess; it never suppresses direct evidence.

The grade is derived at aggregation time rather than stored, because it depends on the versioned
exclusion list: deriving it means the same captured run can be re-graded against a better list,
which a frozen grade could not. The one exception, and its cost, is a redacted run, which has no
hostname left to apply a list to (`runs/README.md`).

## What this doctrine costs

It costs claims. A vendor that infers can say "we caught the leak" more often; we can only say "here
is the fragment that literally matched." It costs coverage: paraphrase and hosted remote servers are
outside what we can prove. The trade is deliberate: a smaller set of claims that are each auditable
and reproducible, over a larger set that are each an inference.
