# Doctrine

The standing rules this repository operates under. They descend from the author's prior work
and are restated here because every design decision in the code cites one of them. When a code
comment says "negativa 3" or "rule 6", this is the referent.

## The four negatives (never)

1. **Never inject.** Nothing is planted inside a third party: no marker, no token, no code, no
   identifier smuggled into a call toward someone else's system. The observer lives at the own
   edge and watches bytes leaving the machine and bytes coming back. A marker that travels the
   chain cannot be passive and report at the same time, and planting one is an attack surface,
   a terms-of-service problem, and, with customer data, a data-minimization problem. So we do
   not.

2. **Never store content.** Only salted digests and references. The collector may see payloads
   that carry personal data, so what survives memory is a fingerprint, never a byte. The only
   sentence it can emit is: "the fragment with hash X, from reference Y, appeared in the output
   toward domain Z." Enforced in `src/mcpfanout/redact.py`.

3. **Never infer.** A literal match is auditable evidence with a quantifiable false-positive
   rate. Paraphrase, semantic propagation, and "the model probably reworded it" are inference,
   a different product and a different epistemics. If a server re-encoded a value before
   sending, we miss it and say so; we do not guess. This is why matching is byte-literal and
   why NeuroTaint-style semantic tracking is explicitly out of scope (see docs/METHOD.md).

4. **Never act on what is observed.** Observe and record. Do not block, redact in flight, alter,
   or intervene. This is not a gateway or a firewall. The whole product is evidence, not
   enforcement. It is the negative that shapes everything: it forces the edge-observer design
   and forbids the marker.

## The boundary of negative 3: structure is decomposed, meaning is not

Negative 3 forbids inference. It does not forbid PARSING, and the difference needs a line rather
than a habit, because F2 moves the matcher from literal k-grams to structural tokens and a reader
is owed the rule that separates the two.

**Allowed, because it is deterministic and reversible in principle:** splitting a URL into host,
path segments and query values per RFC 3986; percent-decoding and plus-decoding those; walking a
JSON document to its scalar leaves. Each of these recovers a structure the sender put there, with
a published algorithm, and a second implementation of the same rule gets the same answer.

**Forbidden, because each one guesses what the sender meant:** case folding, stemming or
lemmatising, edit distance or any fuzzy comparison, synonym expansion, embeddings or any learned
representation, and tokenising prose into words. A miss is a false negative, which is the safe
direction, and it stays the safe direction only while nothing in the matcher is allowed to
"nearly" match.

The test of a proposed step is not whether it improves recall. It is whether two independent
implementations of the written rule must agree on every input. Percent-decoding must. Stemming
need not.

## Digests of short tokens are obfuscation, not control

Negative 2 says only salted digests and references survive memory. That is still true, and it is
no longer sufficient on its own, because F2 changes what gets digested.

A keyed digest of a 22-byte window of natural language is a fingerprint: the space of inputs is
too large to enumerate. A keyed digest of a structural token is not. `docs`, `deploy`, `warn`,
`acme`, `en-US`, a status, a ref name, a four-digit code: these are dictionary words and enums of
three to six bytes, and anyone holding the key recovers them by enumeration in seconds. This is
not a new discovery, it is `redact.py` PENDING gap 2 arriving on the main path: that note already
names the class it cannot protect, and structural tokens ARE that class. The 22-byte window had
been acting as an accidental privacy floor, and decomposing to tokens removes it.

**So: for short tokens, a keyed digest is obfuscation, not access control.** It raises the cost of
a casual read and it does not bound a determined one. Anything built on it must be built as if the
tokens were recoverable by whoever holds the evidence file.

And the key does not close it, because of where the threat is. A per-installation key protects the
evidence from an OUTSIDER who obtains the file without the key. The people who read an evidence
file in the normal course of their work are insiders, and they hold the key by construction. An
audit trail whose threat model is "somebody inside reads what the agent sent" is not protected by
a key that same person holds. PENDING gap 1 is therefore necessary and not sufficient, and both
PENDING gaps in `redact.py` are promoted here from pre-deployment to-dos to PRECONDITIONS of
deploying the structural matcher outside a measurement.

### The option this leaves open, and it is not chosen here

There is a design that keeps most of the evidence value while persisting far less: store the
digest of the ORDERED TUPLE of a call's structural tokens, plus the token count, and never persist
the individual token digests at all. The individual digests would exist in memory during the
matching pass and be discarded with it, exactly as raw payloads already are.

What it buys: a tuple digest over four tokens is not enumerable the way four separate three-byte
tokens are, so the dictionary attack above stops working against the stored artifact.

What it costs, and this is the trade-off that has to be weighed rather than waved at: containment
is a SUBSET test, and a tuple digest only supports an EQUALITY test. A call whose tokens are all
present in a request plus one more would no longer match, so partial containment becomes
invisible. That is a recall cost of unknown size, and it is unknown because nobody has measured
it.

**It also collides with threat 16 and that collision is the real decision.** Threat 16 asks
whether a match that enters the numbers can be re-derived from what was persisted, which is the
first property an external auditor presses. Persisting only a tuple digest makes a match
LESS re-derivable, not more: an auditor handed a tuple digest and a count can confirm that two
token sets were identical and can confirm nothing about which tokens they were or why the matcher
called it a match. Persisting individual token digests makes the match fully re-derivable and
makes the tokens recoverable by anyone holding the key. Privacy and auditability are pulling in
opposite directions here, and the honest statement is that this repository has measured neither
side of it.

This option is recorded, not adopted. Choosing it is a decision for whoever owns the deployment,
made with threat 16 open on the desk, and it is deliberately left unmade here.

### The legal status of what we store, stated plainly

A keyed hash of a personal data item is **pseudonymised data, not anonymised data**, under
recital 26 of the GDPR, and it remains within the scope of the Regulation.

This sentence is in the doctrine rather than in a compliance appendix because it changes what may
be claimed. "We only store hashes" is not a statement that the regulation stops applying. A
fingerprint that can be matched back to a call, by a party holding the key, is data relating to an
identifiable person whenever the underlying fragment was. Every retention, access and erasure
obligation that would apply to the fragment applies to the digest of it.

## The evidence model: three separate claims

This replaces the single `EFECTIVO` / `DECLARADO` / `INDETERMINADO` column. That column asked
three questions and answered with one word, so it could answer none of them precisely. The three
claims are recorded and reported separately, and **they never appear together in one sentence**,
because a sentence that joins them is the conflation returning.

| Claim | Question | Where |
| --- | --- | --- |
| Occurrence | was the transfer observed, and readable | number 4, `occurrence_counts` |
| Provenance | did the request carry recognisable material of ours | number 4, `provenance_counts` |
| Attribution | could it be tied to a tool call, and how strongly | number 5, `attribution_grades` |

**Occurrence**: `observed` (TLS terminated, request read) or `connection_only`. An unreadable
request yields provenance `unknown`, never `none`: "we looked and found nothing" and "we could
not look" are different findings, and collapsing them is how a blind spot reads as a clean
result.

**Provenance**: `none`, `context` (material from a session context file), `arguments` (material
from a driven call's arguments), `both`, or `unknown`. A context match is a leak claim; an
argument match is a causal key. Different questions, kept apart.

**Attribution is a graded dimension**, strongest first. A grade is a claim about the QUALITY OF
THE EVIDENCE, never about certainty of cause.

- `TRACE_PROPAGATED`: our exact W3C `traceparent` appeared in the outbound request.
- `CONTENT_UNIQUE`: more than one call was in flight and the matched fragment was present in
  exactly one of them. Candidates existed and content told them apart.
- `CONTENT_AMBIGUOUS`: more than one call in flight, fragment in several. Content matched and
  did not discriminate. A real outcome, and the one that bounds precision.
- `CONTENT_MATCH_UNCONTESTED`: a match with only one call in flight. Honest and weaker, because
  there was nothing to tell apart.
- `TEMPORAL_ONLY`: a time window and a pid, and nothing else. Correlation, called correlation.
- `UNATTRIBUTED`: no evidence, or the flow was ineligible. Always with a named reason.

### The tautology this design exists to avoid

The corpus is driven sequentially, so in every window there is exactly one call in flight. If
`CONTENT_UNIQUE` meant "the fragment matched and nothing competed", it would be true of every
match by construction, and the harness would publish 100% strong attribution having
discriminated nothing. That is a restatement of the experimental setup wearing a measurement's
clothes.

So `CONTENT_UNIQUE` requires `active_calls_in_window > 1`. **Today the harness emits none**, and
`tests/test_evidence_model.py` asserts that it emits none. The question this project exists to
answer, whether content matching recovers attribution when time cannot, is answerable only with
concurrent calls, which is phase C (`docs/PHASES.md`). Strong attribution counts
`TRACE_PROPAGATED` and `CONTENT_UNIQUE` only; `CONTENT_MATCH_UNCONTESTED` is deliberately
excluded from it.

### Ineligibility is not correlation

The first real capture produced 90 flows that the old column called `DECLARADO`, of which 87 were
a package registry that cannot carry a tool call's arguments at all. `DECLARADO` asserted
temporal correlation where the truth was ineligibility. Those flows are now `UNATTRIBUTED` with
the reason named: *ineligible: package infrastructure traffic, carries no tool-call arguments*.

Eligibility is checked **after** trace and content evidence, never before. A package-registry
flow that did carry our traceparent, or a literal fragment of a call's arguments, is attributed
on that evidence and stays visible. The declared exclusion list
(`registry/package-infrastructure.json`) withholds a temporal guess; it never suppresses direct
evidence. Same principle as number 1 never filtering its raw count.

Implemented in `match.decide_occurrence`, `match.decide_provenance` and
`match.grade_attribution`. The grade is derived at aggregation time rather than stored in the
record, because it depends on the versioned exclusion list: deriving it means the same captured
run can be re-graded against a better list, which a frozen grade could not.

## Never discard unstaged work

`git checkout -- <path>` and `git restore <path>` are forbidden on work that is not staged. To
discard something, use `git stash push -m "<why>"`, which is recoverable. Stated here as well as
in CLAUDE.md because this file is the one the code comments cite.

The pattern is specific and it recurred three times in one session: a file is mutated on purpose
to prove a test bites, `checkout` is used to undo the mutation, and everything else unstaged under
that path returns to HEAD with it. Back up outside the repository before mutating, or stage first.

## Rule 6: no number without a command

No published figure exists without a command that measures it. Every one of the six numbers has
a `make` target and an `aggregate` subcommand behind it. A claim in a README that cannot be
reproduced by running a command is not allowed to ship. See `docs/THE-SIX-NUMBERS.md`.

## Rule 10: an absent instrument must fail, not pass quietly

A test that only catches a WRONG instrument leaves the dangerous case uncovered, because a wrong
number gets investigated and a green gets published. This repository has produced that failure
seven times: an addon that did not load and finished green with zero flows, a k constant that
diverged and silently stopped matching, a selftest that serialised the structural fields without
ever populating one, a committed figure that omitted the very denominator its verdict is measured
against, a version number that two files of this repository disagreed about while both validated, a
README that contradicted three measured facts for four days, and four calibration figures that
stopped reproducing for eight commits while a test that checked their SHAPE stayed green. The last
three extend the rule past code: a document is an artifact, so is a metadata field, and so is a
committed figure. Full statement and all seven instances in `docs/THE-GATE.md`, rule 10.

The rule applies to itself: a detector must be shown to detect a planted instance, in the same
run, through the same code path, before its clean report means anything.

## Responsible disclosure

If a server egresses to a destination its own documentation does not declare, the run stops and
flags it, and nothing that locates that server is published until authorized. Aggregate output
names no server, host, or tool. See `docs/THE-GATE.md`, rules 3 and 7.

## What this doctrine costs

It costs claims. A vendor that infers can say "we caught the leak" more often; we can only say
"here is the fragment that literally matched." It costs coverage: paraphrase and hosted remote
servers are outside what we can prove. The trade is deliberate: a smaller set of claims that are
each auditable and reproducible, over a larger set that are each an inference.
