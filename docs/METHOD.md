# Method, and the six numbers

What is measured, how it is observed, and what each of the six numbers is for. The order in which
things may be measured, and the conditions a run must satisfy before a number from it is reported,
are in [`PROTOCOL.md`](PROTOCOL.md).

**What this measurement serves.** If the numbers justify building, the product is *runtime
provenance and evidence for autonomous agents*, with MCP as the first supported environment rather
than the category. The consequence for this document is concrete: the observation model is written
in terms of an agent's action and its egress, never in terms of MCP messages, so that a second
environment is an adapter and not a rewrite.

## Why measure before building

You cannot design the causal-union layer without knowing the fan-out, and choosing blind means
building the wrong architecture. If the average MCP server opens one connection per tool call, to
its own API, the union is trivial and the product is content matching alone. If it opens forty
concurrent connections to distinct domains, the union is the whole product and content matching is
critical infrastructure. These are two different systems, and the measurement picks which one is
real.

## The observation model: the own edge

Three questions matter, and all three are answered without injecting anything, because all three
happen before bytes leave the machine or after they return.

| Question | Where it is observed | Needs injection |
| --- | --- | --- |
| Which third party the call went to | DNS, TLS SNI, the socket | No |
| Which fragments of my system left | The outbound request body and target | No |
| What came back into context | The response body | No |

The observer lives at the own edge. It never plants a marker in a third party, because a marker
cannot be passive and report at the same time, and because a chain deeper than the first
non-self-hostable node is not observable by anyone without cooperation. That limit is physical, and
the harness states it as a result rather than as an apology.

## The capture layer: why a proxy, not eBPF, for the measurement

To read the plaintext of an HTTPS body you must terminate the TLS. Three ways: a proxy with our own
CA in the process trust store; configuring the process with `HTTPS_PROXY`, which is what the
harness does; or eBPF uprobes on `SSL_write` and `SSL_read`, capturing plaintext before it is
encrypted, which is the technically correct one because it also catches certificate-pinned clients
and needs no CA, and which is Linux and kernel specific.

For a measurement of this size the proxy is the right cost, and eBPF is the product-grade layer,
out of scope here and documented as the next one. **The proxy's blind spots are not a caveat, they
are the headline finding**: a client that does not honour the two environment variables is
invisible to it, whatever its configuration, and the pcap backstop (`make backstop`) is the only
thing that says so. See [`THREATS.md`](THREATS.md), threat 19.

### The protocol revision we speak, and the one SEP-414 landed in

Two different revisions, and the distinction is load-bearing. The wire the driver implements is
**2025-11-25**: `initialize`, `notifications/initialized`, `tools/list`, `tools/call`.
`mcpfanout.driver.PROTOCOL_VERSION` says so, and `harness/probe.py` negotiates down from there.

The **current** revision is 2026-07-28 and we deliberately do not speak it: it removed the
handshake entirely, every request carrying its own `io.modelcontextprotocol/protocolVersion` in
`_meta` with a `server/discover` RPC (SEP-2575). Announcing `2026-07-28` inside an `initialize`
request, which this harness did until the defect was found, describes a protocol neither side is
speaking. Speaking it properly is a driver rewrite, and no reference server implements it yet.

The convention this harness relies on, trace context in `_meta` under `traceparent`, `tracestate`
and `baggage`, is **SEP-414**, which is Final and is a minor change of that same 2026-07-28
changelog. So the convention is documented one revision ahead of the wire we speak, which is
legitimate: `_meta` is an open extension field in both revisions. It is also not an injection under
negative 1: the request goes to a server we launched ourselves, on our own machine, and nothing is
planted in a third party. Whether the server forwards it downstream is the server's own choice, and
observing that choice is number 3.

## Half B is the join key of Half A

The hard problem of attribution is tying an outbound connection to the call that caused it. If a
server serves five calls at once, the clock and the pid do not say which of the five opened a
socket. This is why prior art attributes to process (ARMO) or settles for time-and-session
correlation (AegisMCP).

If a fragment of the call arguments appears literally in the outbound payload, that is causal
evidence rather than correlation. Content matching (Half B) supplies the join key that attribution
(Half A) lacks. They are not two functions summed; they resolve each other.

## The privacy model: digest-only

Storage keeps salted digests and references, never content. The stored sentence is: "the fragment
with hash X, from reference Y, appeared in the output toward domain Z." The salt is keyed into a
BLAKE2b hash so a stored fingerprint cannot be confirmed by a dictionary of candidate secrets. The
numbers are invariant to the salt, since they are counts over set intersections, so a secret salt
in a real deployment changes what is stored but never what is reported. Reproducibility uses a
fixed default salt. Two gaps are recorded as preconditions of any deployment rather than as
to-dos, in `src/mcpfanout/redact.py`: a per-installation key with rotation, and a
minimum-fragment-length policy, because for a short token a keyed digest is obfuscation rather than
control.

## The matching technique, and why there are two matchers

Indexed Document Matching: rolling hashes over overlapping fragments, fifteen years old in DLP
production, reimplemented in the standard library (`src/mcpfanout/shingle.py`). k = 22 bytes, chosen
by the sweep in [`CALIBRATION.md`](CALIBRATION.md) rather than by judgement. Winnowing (Schleimer,
Wilkerson, Aiken) selects a deterministic subset of fingerprints with a guarantee that any shared
substring of at least w + k - 1 = 29 bytes is detected; it is used for the persisted digests only,
so it never changes a number.

The academic counter-argument (NeuroTaint) is that exact matching is the wrong technique, because
propagation through an LLM is linguistic and probabilistic and a paraphrase breaks the hash. The
answer: literal matching produces auditable evidence with a measured false-positive rate; semantic
tracking produces inference. They are different products and the doctrine already chose.

**Two instruments, because there are two problems.** Numbers 4 and 5 were measured with one matcher
until F2, and that was a mistake with a measured cost.

- **Number 4 keeps the exact k-gram.** It asks whether a request carried material from a session
  context file. Context files are prose: long, unstructured, no field boundaries to exploit. F2 did
  not move a single one of its figures, verified byte-identical against the committed figure.
- **Number 5 moves to structural containment.** It asks whether a request was CAUSED by a specific
  call, and a call's arguments are not prose: they are JSON fields whose values reappear on the wire
  as path segments and query values. The diagnosis is one line of data: `/docs/deploy/runbook` is 20
  bytes and invisible at k = 22, while `/docs/deploy/checklist` is 22 bytes and visible. A matcher
  whose sensitivity depends on how a documentation site happened to name a page is measuring the
  site.

The criterion is containment: every structural token of the call present in the request, compared as
sets of keyed digests so no token crosses in plaintext. Self-match went from 0.5000 to 1.0000 on the
negative control and from 0.5385 to 1.0000 on real material, with 0 of 280 false positives on the
reserved half. The two matchers share no code path and `aggregate` reads one for number 4 and the
other for number 5; the cost is that the repository carries two matchers and has to keep both
calibrated, which is the honest price of the split rather than an oversight.

**What containment cannot do, in the method rather than in the code.** A call whose tokens are a
proper subset of a concurrent call's cannot be uniquely attributed by any implementation of
containment, and the commonest way to produce one is an agent re-reading its own document with more
precision. [`THREATS.md`](THREATS.md) threat 18 carries the argument and the measured instance, and
number 5 publishes the count of such calls so the limit is visible in the output.

## The two matched channels (numbers 4 and 5)

Every outbound request is matched on its **request target** (path plus query, exactly as it goes on
the wire) and on its **body**, separately. Three constraints, each a correctness requirement:

1. **The target, never the absolute URL.** Scheme and host are not content drawn from our context.
   Including them would manufacture self-matches while saying nothing about what left.
2. **The two channels are never pooled into one figure.** A causal match in a query string and one
   in a body are both literal evidence and they are not the same claim, and a single combined figure
   is indistinguishable from one inflated with URLs. Totals are given too, labelled as totals.
3. **Matching stays byte-literal, so it stays digest-only.** The target is shingled and hashed
   exactly like the body.

This was a change of definition, made deliberately. Until it was made only the body was matched, so
numbers 4 and 5 were structurally zero for every GET-based server, and the first real capture
demonstrated exactly that: the canary rode in the URL, was on the wire, and the flow recorded no
provenance at all. Residual limit, in the safe direction: a value the client percent-encodes,
base64s or splits across parameters is not detected.

## The recursion: advancing the edge

If the observer only sees the hop leaving the machine, why not move the edge forward: host the third
party too, and from that vantage watch its hop to the fourth?

One rule governs it: **you can only observe the egress of a process you host.** The third-to-fourth
link happens entirely on the third's infrastructure, where there is no socket and no proxy of ours.

- **Where it works:** the self-hostable sub-graph. This is strictly stronger than the cooperative
  SEP-414 path, because it does not ask the server's permission and works against a server that
  refuses to emit `traceparent`.
- **Where it breaks:** the first remote, non-self-hostable node, usually a hosted SaaS API, which in
  a typical MCP graph is a leaf. The harness names that node: observable up to here, broken here,
  for this reason.

Number 6 sizes it. Predicting what a non-hostable node would forward, with a model in the loop, is
inference rather than observation (negative 3) and never enters a number.

## The six numbers

Each has one definition, one thing it decides, and one command (rule 6). The commands default to
the committed redacted runs (`runs/README.md`), so every figure below is recomputable offline.

### Two blocks of metrics, and what each may conclude

**Instrument block, bench only (phase A), where ground truth is known because we built the servers
and the destinations**: capture recall, attribution precision, false provenance matches. These
cannot be computed against real servers at all: recall needs a denominator of known transfers and
precision needs a known cause, so quoting either from a phase B run would be quoting a number with
no denominator.

**Phenomenon block, real servers (phase B)**: the six below.

**No means.** Every per-call distribution reports p50, p95 and max, and no mean. The mean misleads
on exactly these shapes: the first real capture had one call at 89 connections and one at 2, giving
a mean of 45.5, a figure no call produced. Percentiles are nearest-rank, never interpolated, so
every published figure is a value some call actually produced.

**Deliberately out of scope: CPU and latency overhead.** It decides nothing about whether the
phenomenon is real or whether attribution works.

### Number 1: outbound connections per tool call, in three figures

Per call, three distributions over all calls including those that produced zero egress, each as n,
p50, p95 and max, and **published together, always**: `connections_raw`, every observed connection
unfiltered; `distinct_hosts`, the same quantity as number 2; and
`connections_excluding_package_infrastructure`, raw minus the hosts on the declared list.

**Why three and not one.** The first real capture proved it rather than suggested it:
`mcp-server-fetch` opened 87 connections to a package registry while serving a single call, because
it installs an npm package at tool-call time, giving a raw mean of 45.5. The number is true and it
answers the wrong question: those 87 are serial connections to one host of package infrastructure
during a known, single active call, so they are trivially attributable. What this number decides
turns on concurrent connections to DISTINCT domains, and by that measure the same call has 2.

**The exclusion list is declared, not a silent filter.** `registry/package-infrastructure.json`:
committed, versioned by date, containing only hosts whose sole purpose is distributing software
packages. The aggregate cites it by name, version and sha256, and the citation carries no hostname,
because gate rule 3 forbids one in published output. General-purpose CDNs are deliberately NOT on
it, because they also carry ordinary application traffic and listing them would hide real egress.
If the list cannot be loaded the third figure is `null` with the reason named, never computed
against an empty list: "no list" and "no package traffic" would otherwise look identical.

**Decides** whether the causal union is trivial or is the product. **Command** `make n1`.
**Caveat**: the proxy sees only HTTP(S) it can terminate, so this is a floor, stated as a floor and
bounded by the pcap backstop.

### Number 2: distinct domains per tool call

Per call, the count of distinct destination hostnames, as a distribution. **Decides** the size of
the publishable finding: domain sequences alone leak information, and the local-research-agent study
recovered most of a prompt's functional intent from the domain sequence alone. **Command**
`make n2`.

### Number 3: fraction of servers that propagate `traceparent`

Of the servers driven, the fraction for which at least one outbound request carried the exact W3C
`traceparent` we set in `params._meta`, **segmented by the protocol revision the server answered
with**, plus the pooled figure.

**Why segmented.** SEP-414 is a minor change of the 2026-07-28 revision, so a server answering
`2024-11-05` predates the convention being written down and "it does not propagate" is a fact about
its age. Pooling distorts in both directions. The pooled figure is still published, because
withholding it would be its own distortion, but the segments are the answer. **Decides** whether the
cooperative path is worth anything today. **Command** `make n3`.

### Number 4: provenance coverage

Two of the three evidence claims, reported together because neither means anything alone:
**occurrence**, how many flows were `observed` against `connection_only`, and **provenance**, how
many carried `none` / `context` / `arguments` / `both` / `unknown` material of ours, plus the bytes
covered by exact k-gram interval union, per channel. The third claim, attribution, is number 5's and
is never joined to these in one sentence. **Decides** whether content matching has signal at all.
**Command** `make n4`. A match shorter than k is not counted, which is the safe direction.

### Number 5: distribution of attribution grades

Of all outbound connections, the count in each grade, with the named reason for each, the channel
split, and the declared lists that graded eligibility, cited by name, version and digest.
**Strong attribution counts `TRACE_PROPAGATED` and `CONTENT_UNIQUE` only**;
`CONTENT_MATCH_UNCONTESTED` is deliberately excluded, because a match with one call in flight
discriminated nothing. There is no single "causally unifiable" fraction: that figure counted every
content match as strong evidence when nothing had been told apart.

**Which pass it may be read from, and the output says which one produced it.** Under the SEQUENTIAL
pass the number emits `sequential_driving: true` and its strong-attribution figure is a restatement
of the driving regime rather than a result. Under the CONCURRENT pass the same distribution is the
measurement, and the output carries the one thing a reader is invited to assume and must not: there
is **no ground truth in that pass**, so nothing there says a strong attribution was correct.
Precision has a denominator only on the bench.

**Reported per rung, not only pooled.** `grades_by_window_size` keys the counts by how many calls
were in flight: "strong attribution was X%" is unreadable without the N it was measured at.

**Published as a lower bound, and it may not be published without saying so.** The sensor's
self-match recall on realistic argument material is below 1: over the five realistic families of the
negative corpus it is 0.4, so most of the material the sensor is shown does not match itself even
when the call is its own cause and nothing is concurrent. An attributable share measured that way is
a floor. The aggregate carries it as `published_as`, so the figure travels with the caveat rather
than beside it. **Decides** whether the whole product works. **Command** `make n5`.

**Honest denominator.** An argument-less call ("list my files") has nothing to match and falls to
`TEMPORAL_ONLY` or `UNATTRIBUTED` by construction. That split is itself a publishable result.

### Number 6: fraction of touched third parties that are self-hostable

Of the distinct destination nodes touched, the fraction that are self-hostable (local, or a
self-hostable MCP node) against remote leaves. **Decides** how far the edge observer can advance
before the chain breaks. **Command** `make n6`. **Conservative rule**: an unknown public domain
counts as a remote leaf, because claiming self-hostability we do not have would inflate the
recursion's reach.

## Credentials: what was decided, and what it changed

Gate rule 5 requires lab accounts rather than no credentials, because an uncredentialed server can
be silent in a way that produces no data at all: `brave-search` exits before the handshake without
its key, so there is no failed call to observe. What was actually created, and why:

| Server | Decision | Cost | Why |
| --- | --- | --- | --- |
| github | **created**, free tier, token with no scopes | 0 EUR, ~10 min | already pinned, probed and in both corpora; the most tool-rich server in the set |
| brave-search | rejected | n/a | free tier requires a credit card (checked 2026-09-19), which is a payment instrument attached to an automated lab |
| google-maps | rejected | n/a | same, plus it is not in `registry/servers.yaml` at all: half a day of repository work before an account helps |
| slack | rejected | n/a | not in the registry either, and it buys no new KIND of observation: it is an ordinary HTTPS API like the two above |

**The result was instructive and is the reason this table is short.** The github token worked and
changed no published number, because that server's client ignores the proxy (threat 6, re-measured
with 10 direct SYNs). Do not credential another server whose client ignores the proxy until
transparent interception or eBPF exists: the credential buys a connection nobody can read.

**Terms of use are asked, not answered.** The same standard as
`registry/declared-destinations.json`: asserting what a document says without having read it is the
plausible guess this project keeps finding in its own history. The questions to put to each
provider's current terms are whether automated access is permitted and under what identification,
whether a named rate limit makes a wave of 10 a breach or a 429, whether responses may be stored
(our design stores salted digests and counts, never content, which is the favourable side), whether
benchmarking or publishing measurements is restricted, and whether lab accounts are permitted at
all.

**What credentials do not solve.** Three of the ten servers are abandoned upstream and one is marked
deprecated with its last release in 2024. A credential does not make an abandoned server
representative of anything. The set is what it is, and the write-up says so.
