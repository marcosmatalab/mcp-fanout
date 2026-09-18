# Method

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

## Cost

One afternoon, about 10 EUR of compute. It touches nothing outside a container and starts no server
against real credentials. The stop criteria (docs/STOP-CRITERIA.md) say when to stop spending.
