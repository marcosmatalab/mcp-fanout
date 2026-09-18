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

## The three states

Every outbound connection resolves to exactly one state. The harness publishes the percentage
of each; that is measurement, not a promise.

- `EFECTIVO`: a fragment of the causing call's arguments appears literally in the outbound
  payload. This connection was caused by this call, with the citation. Content evidence, not a
  temporal guess.
- `DECLARADO`: only a time window and a pid are available. Stated as correlation, called
  correlation.
- `INDETERMINADO`: the payload was not observable (TLS we did not terminate, an argument-less
  call, an async pool), with the cause named.

Implemented in `match.decide_state`. Content evidence outranks correlation: if a call's
arguments are in the payload, the connection is `EFECTIVO` no matter how many other calls were
concurrent.

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

## Responsible disclosure

If a server egresses to a destination its own documentation does not declare, the run stops and
flags it, and nothing that locates that server is published until authorized. Aggregate output
names no server, host, or tool. See `docs/THE-GATE.md`, rules 3 and 7.

## What this doctrine costs

It costs claims. A vendor that infers can say "we caught the leak" more often; we can only say
"here is the fragment that literally matched." It costs coverage: paraphrase and hosted remote
servers are outside what we can prove. The trade is deliberate: a smaller set of claims that are
each auditable and reproducible, over a larger set that are each an inference.
