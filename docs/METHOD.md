# Method

**What this measurement serves.** If the numbers justify building, the product is *runtime
provenance and evidence for autonomous agents*, with MCP as the first supported environment
rather than the category. Deliberately not "MCP security", which binds a product to a protocol
that is still changing and to a function a gateway absorbs; and deliberately not "data lineage",
which is an occupied category with an incumbent that has brand and capital. See README.md. The
consequence for this document is concrete: the observation model below is written in terms of an
agent's action and its egress, never in terms of MCP messages, so that a second environment is an
adapter and not a rewrite.

## The three phases

The instrument is measured before the phenomenon: a controlled bench of our own servers (phase A),
then the real pinned servers (phase B), then an attack on our own attribution with concurrent
calls (phase C). Phase A blocks phase B, as gate rule 8. Recall and precision exist only on the
bench, because only there is there a denominator of transfers we caused and a known cause to check
a claim against. Full definitions, cases and pre-registered gates: `docs/PROTOCOL.md`.

## Why measure before building

You cannot design the causal-union layer without knowing the fan-out, and choosing blind means
building the wrong architecture. If the average MCP server opens one connection per tool call, to
its own API, the union is trivial and the product is content matching alone. If it opens forty
concurrent connections to distinct domains, the union is the whole product and content matching is
critical infrastructure. These are two different systems. The measurement picks which one is real.

## The observation model: the own edge

Three questions matter, and all three are answered without injecting anything, because all three
happen before bytes leave the machine or after they return.

| Question | Where it is observed | Needs injection |
| --- | --- | --- |
| Which third party the call went to | DNS, TLS SNI, the socket | No |
| Which fragments of my system left | The outbound request body | No |
| What came back into context | The response body | No |

The observer lives at the own edge. It never plants a marker in a third party, because a marker
cannot be passive and report at the same time, and because a chain deeper than the first
non-self-hostable node is not observable by anyone without cooperation. That limit is physical.
The harness states it as a result, not an apology (see "The recursion" below).

## The protocol revision we speak, and the one SEP-414 landed in

These are two different revisions and the distinction is load-bearing, so it is stated rather
than left to be inferred from a constant.

The wire the driver implements is **2025-11-25**: `initialize`, `notifications/initialized`,
`tools/list`, `tools/call`. `mcpfanout.driver.PROTOCOL_VERSION` says so, and
`harness/probe.py` negotiates down from there through the older handshake revisions.

The **current** revision is 2026-07-28, and we deliberately do not speak it. It removed the
handshake entirely: every request carries its own `io.modelcontextprotocol/protocolVersion` in
`_meta` and servers must implement a `server/discover` RPC (SEP-2575, major changes 2 and 3 of
<https://modelcontextprotocol.io/specification/2026-07-28/changelog>). Announcing `2026-07-28`
inside an `initialize` request, which is what this harness did until the defect was found,
describes a protocol neither side is speaking. Speaking it properly is a driver rewrite, not a
constant, and no reference server implements it yet; the servers in the registry answer
2025-11-25.

The convention this harness relies on, trace context in `_meta` under the unprefixed keys
`traceparent`, `tracestate` and `baggage` in W3C Trace Context format, is documented by
**SEP-414**, which is Final (<https://modelcontextprotocol.io/seps/414-request-meta>) and is
minor change 2 of that same 2026-07-28 changelog. So the convention we use is documented one
revision ahead of the wire we speak. That is legitimate: `_meta` is an open extension field in
both revisions, so the key is carried by a field built to carry it. It is also not an injection
under negativa 1 (docs/DOCTRINE.md): the request goes to a server we launched ourselves, on our
own machine, and nothing is planted in a third party. Whether the server then forwards it
downstream is the server's own choice, and observing that choice is number 3.

## The capture layer: why a proxy, not eBPF, for the measurement

To read the plaintext of an HTTPS body you must terminate the TLS. There are three ways:

1. A proxy with our own CA in the process trust store. Works for locally launched servers, is
   interception, and is declared as such. One dependency, no kernel privileges.
2. Configuring the process with `HTTPS_PROXY`. What the harness does: the server inherits the
   proxy env and its HTTP(S) egress passes through mitmdump.
3. eBPF uprobes on `SSL_write` and `SSL_read`, capturing plaintext before it is encrypted. The
   technically correct one: it also catches certificate-pinned clients and needs no CA. It is what
   ecapture, Pixie, and AgentSight do. It is Linux and kernel specific.

For a one-afternoon measurement, the proxy is the right cost. eBPF is the product-grade layer and
is out of scope here, documented as the next layer. The proxy's blind spots (non-HTTP,
pinned TLS) are covered by a pcap backstop that counts connections the proxy could not read, so
the fan-out numbers are honest floors.

## Half B is the join key of Half A

The hard problem of attribution is tying an outbound connection to the call that caused it. If a
server serves five calls at once, the clock and the pid do not say which of the five opened a
socket. This is why prior art attributes to process (ARMO) or settles for time-and-session
correlation (AegisMCP).

If a fragment of the call arguments appears literally in the outbound payload, that is causal
evidence, not correlation. Content matching (Half B) supplies the join key that attribution
(Half A) lacks. They are not two functions summed; they resolve each other. The measurement drives
calls sequentially so it has ground-truth attribution, and then measures how often content matching
alone would have recovered it (number 5). That recall is the viability of the whole idea.

## The recursion: advancing the edge

The natural next question: if the observer only sees the hop leaving the machine, why not move the
edge forward? Take the third party, host it too under the same harness, and from that new vantage
watch its hop to the fourth. The fourth is then treated as a third, and so on.

One rule governs the whole thing: **you can only observe the egress of a process you host.** On
the second-to-third link you sit on the second's side, because the second runs on your machine.
The third-to-fourth link happens entirely on the third's infrastructure, where you have no socket
and no proxy. So "treat the fourth as a third" is possible only if you can also host the fourth.

- **Where it works:** the self-hostable sub-graph. If the third party is itself a self-hostable
  MCP server, you host it, re-proxy, and go one level deeper. This is strictly stronger than the
  cooperative SEP-414 path: it does not ask the server's permission and works even against an
  adversary that refuses to emit `traceparent`, as long as it does not detect the re-hosting.
- **Where it breaks:** the first remote, non-self-hostable node, usually a hosted SaaS API, which
  in a typical MCP graph is a leaf. The harness names that node: observable up to here, broken
  here, for this reason.

Number 6 sizes this. A shallow self-hostable interior means the recursion buys nothing; a deep one
makes it critical. The generic form of the harness (one adapter that wraps any node you can run,
rather than a recipe per server) is what makes the recursion practical; it cannot confer
self-hostability on a node you do not possess.

Determinism note: the recursion is observational and deterministic. Predicting what a non-hostable
node would forward, with a model in the loop, is inference, not observation (negativa 3), and never
enters a number.

## The privacy model: digest-only

The collector captures payloads that may carry personal data. Storage keeps salted digests and
references, never content. The stored sentence is: "the fragment with hash X, from reference Y,
appeared in the output toward domain Z." The salt is keyed into a BLAKE2b hash so a stored
fingerprint cannot be confirmed by a dictionary of candidate secrets. The numbers are invariant to
the salt (they are counts over set intersections), so a secret salt in a real deployment changes
what is stored but never what is reported. Reproducibility uses a fixed default salt.

## The matching technique

Indexed Document Matching: rolling hashes over overlapping fragments, fifteen years old in DLP
production. We reimplement it in the standard library (`src/mcpfanout/shingle.py`).

**What is matched: two channels, counted apart.** Every outbound request is matched on its
request target (path + query) and on its body, separately. Both are bytes leaving the machine
toward a third party. The target is matched, and the absolute URL is not: scheme and host are not
content drawn from our context, and including them would manufacture self-matches. The two are
never summed into one figure, because a causal match in a query string and one in a body are
different claims and a combined number cannot be told apart from one padded with URLs. See
`docs/THE-SIX-NUMBERS.md`, "The two matched channels", for the definition and for why it changed:
matching only bodies made numbers 4 and 5 structurally zero for every GET-based server, which the
first real capture demonstrated rather than predicted. The privacy model is untouched -- the
target is shingled and hashed exactly like the body, and only salted digests are persisted.

- k-gram size k = 16 bytes: long enough that a shared run is not coincidental, short enough to
  catch real secrets.
- Rolling hash: polynomial, base 257, modulus 2**61 - 1. Collision probability is bounded and
  stated where the hash is defined; it is the only genuinely probabilistic quantity in the stack.
- Winnowing (Schleimer, Wilkerson, Aiken): selects a deterministic subset of fingerprints with a
  guarantee that any shared substring of length >= w + k - 1 = 23 bytes is detected. Used for the
  persisted, digest-only artifacts. The numbers themselves are computed by exact k-gram coverage,
  so winnowing never changes a number.

The academic counter-argument (NeuroTaint) is that exact matching is the wrong technique because in
an LLM propagation is linguistic and probabilistic, so a paraphrase breaks the hash. The answer:
literal matching produces auditable evidence with near-zero false positives; semantic tracking
produces inference. They are different products, and the doctrine already chose which one this is.

## Two instruments, because there are two problems

Numbers 4 and 5 were measured with one matcher until F2, and that was a mistake with a measured
cost. They ask different questions over different material.

**Number 4, provenance coverage, keeps the exact k-gram.** It asks whether a request carried
material from a session context file. Context files are prose: long, unstructured, with no field
boundaries to exploit. A literal k-gram at k = 22 is the right instrument there, its
false-positive rate on the negative control is 0.0000, and F2 did not move a single one of its
figures (docs/PREREG-F2.md, P6, verified byte-identical against the committed figure).

**Number 5, attribution, moves to structural containment.** It asks whether a request was CAUSED
by a specific call. A call's arguments are not prose: they are JSON fields whose values reappear
on the wire as path segments and query values. That correspondence is structural, and a k-gram
cannot see it. The diagnosis is one line of data: `/docs/deploy/runbook` is 20 bytes and invisible
at k = 22, while `/docs/deploy/checklist` is 22 bytes and visible. A matcher whose sensitivity
depends on how a documentation site happened to name a page is measuring the site.

The criterion is containment: every structural token of the call present in the request, compared
as sets of keyed digests so no token crosses in plaintext. Measured self-match went from 0.5000 to
1.0000 on the negative control and from 0.5385 to 1.0000 on real material, with 0 of 280 false
positives on the reserved half.

**What makes this a split and not a replacement.** The two matchers share no code path, their
figures are recorded in separate fields of `Flow`, and `aggregate` reads one for number 4 and the
other for number 5. Merging them would have meant choosing one instrument for two problems again,
which is the thing that was wrong. The cost is that the repository now carries two matchers and
has to keep both calibrated, and that is the honest price of the split rather than an oversight.

**What containment cannot do, in the method rather than in the code.** A call whose tokens are a
proper subset of a concurrent call's cannot be uniquely attributed by any implementation of
containment, and the commonest way to produce one is an agent re-reading its own document with
more precision. docs/THREATS.md threat 18 carries the argument and the measured instance, and
number 5 publishes the count of such calls so the limit is visible in the output.

## Cost

**Corrected 2026-09-20.** Earlier versions of this paragraph said "one afternoon and about
10 EUR of compute". Both figures were guesses and both were wrong, and README.md now publishes
the measured table that disproves them. Measured: **0 EUR** of cloud compute, because everything
runs in Docker on one machine; **0 EUR** of paid APIs, the only credential being a free-tier
GitHub token; **138 seconds** of actual driving across 21 capture runs; **two days** of wall
clock. The money cost is genuinely zero and the real cost is attention.

It touches nothing outside a container and starts no server against real credentials. The stop criteria (docs/PROTOCOL.md) say when to stop spending.
