# Draft. Sections 1 and 3 only. Everything else is still `OUTLINE.md`.

---

## Title

**What Your Proxy Cannot See: Measuring Tool-Call Provenance for Autonomous Agents**

Subtitle, if the venue allows one: *a negative result, and the instrument defect that produced
three different answers to the same question*

---

## 1. Abstract

An HTTP proxy selected by the `HTTP_PROXY` and `HTTPS_PROXY` environment variables does not
observe an autonomous agent's outbound traffic. It observes the subset of the agent's clients that
chose to honour two environment variables, and that subset is not knowable in advance: in the
system measured here it silently excluded one of the three components that reached a third party
at all, because Node.js ignores those variables in its global `fetch` unless a flag introduced in
2025 is explicitly enabled.

We measure whether an agent's outbound requests can be attributed to the tool call that caused
them, using byte-literal matching over structural tokens with no content retained and no
inference. Against a threshold of 0.80 fixed and cryptographically sealed before any measurement
existed, the attributable share of call-caused, content-eligible flows is **0.6579**. The
instrument does not meet its own bar, and we report that rather than the two higher figures the
same question yielded while the instrument was blind: 0.8947 and 0.8095. Every fix to the
instrument's observability lowered the headline.

The corrected instrument then found two behaviours in the measured environment, both disclosed to
their maintainers before publication: a tool call that downloads and executes roughly forty
third-party packages while it runs, from unpinned version ranges with no lockfile, resolving
differently on different days; and a server whose embedded browser reaches destinations the
server's own documentation does not declare.

**Contributions.**

1. **An instrument result.** Environment-variable interception is opt-in by the observed. We give
   the causal chain, the one-variable remedy, the runtime versions that have it, what it still
   does not cover, and a packet-level test for what remains invisible. Anyone repeating this
   measurement the obvious way will reproduce the defect before they reproduce anything else.
2. **A negative attribution result**, with its denominators published together and its
   pre-registered threshold missed.
3. **A claim a reader can apply without running anything**: content attribution works on tools
   whose arguments carry structure and fails on free-text tools, under any rule that does not
   manufacture false positives. We give the measured price of relaxing that rule.
4. **A pre-registration apparatus for systems measurement**, independent of the system measured: a
   digest-sealed prediction block, a verdict whose denominator is frozen by hash, held-out corpora
   that are retired once measured, and a rule that every instrument carry a test which fails when
   the instrument is absent rather than merely wrong. One of our own sealed predictions turned out
   to be false. It is still in the seal, uncorrected, with the correction beside it.

---

## 3. The headline: a terminating proxy does not observe a modern Node client

### 3.1 What we were doing, and what we believed

The capture layer is a terminating HTTP proxy inside a container. Each component under measurement
is launched with `HTTP_PROXY` and `HTTPS_PROXY` pointing at it, the proxy's certificate authority
is installed in the container's trust store, and the proxy terminates TLS, hashes each outbound
request in memory, and writes one content-free record per request. A packet capture runs alongside
it as a backstop.

The belief embedded in that design, which we did not state because it did not look like an
assumption, is that configuring a proxy through the environment is a way of intercepting a
process's egress. It is not. It is a way of intercepting the egress of clients that have chosen to
read those two variables, and the choice belongs to each client library rather than to us.

### 3.2 The chain

1. Interception is selected by two environment variables, so it is a property of each client
   honouring a convention, not a property of the network.
2. Python's `requests` and `urllib` honour it. `npm` and `npx` honour it. Chromium honours it.
   **Node.js does not honour it in its global `fetch`**, nor in the `undici` library beneath it.
   This is documented behaviour rather than a defect.
3. Node gained the capability in **22.21.0 and 24.5.0**, and it remains **off by default**. It is
   enabled with `NODE_USE_ENV_PROXY=1` or `--use-env-proxy`.
4. Our container image shipped **Node 20.20.2**, where the switch does not exist at all.

Point 4 is the one that matters for anyone auditing this work: no configuration of our harness
could have made that traffic visible. The defect was not a setting we failed to apply. It was a
runtime that could not apply it, in an image whose Node version nobody had a reason to question,
chosen years of release cadence before the capability existed.

### 3.3 What it looked like from inside the measurement

Nothing. That is the point, and it is why this section is first.

One of the ten components we drove is a GitHub API client. It started, completed its protocol
handshake, accepted a credential, executed sixteen of seventeen tool calls successfully, and
returned GitHub's own answers to each one. Its record in our capture contained **zero outbound
flows**. Every downstream figure treated it as a component that had reached no third party.

There was no error, no warning, and no anomaly in any of our tests. The run was reproducible. The
suite was green. A component that egresses nothing and a component we cannot see are the same
observation, and nothing in the record distinguished them.

### 3.4 The evidence, from packets rather than from reasoning

The packet capture is what settles it, because it is the one part of the instrument that does not
depend on a client's cooperation. Counting outbound TCP SYNs by destination (`make backstop`):

| run | total SYNs | to the proxy (loopback) | to the API's address | flows recorded for that component |
|---|---|---|---|---|
| before the fix | 140 | 64 | **10** | **0** |
| after the fix | 150 | **74** | 10 | **17** |

Read the middle two columns together. Before the fix, the component opened ten connections
straight to the API. After it, the loopback count rises by exactly ten and the count to the API is
unchanged, because those ten connections are now the proxy's own, re-originated after terminating
the client's TLS. The traffic did not appear; it became visible.

Across the whole run, the count of components that completed calls and produced no observable
egress despite being expected to reach a third party fell from seven to zero.

### 3.5 Two published figures were wrong, in a specific way

The failure was not merely silent. It was actively misleading, because a blind component is not
absent from a denominator. It sits in it as a zero.

**Trace-context propagation.** We reported that 0 of 10 components propagated a trace context. A
component whose traffic never reached the proxy did not decline to propagate anything; we never
observed it answer the question. Its zero was a property of our instrument published as a property
of the component. The figure now has a denominator of components with at least one observed
call-caused flow, currently three, with the all-components figure retained beside it and marked
as not comparable.

**Third-party node set.** We reported the self-hostable fraction of the third parties touched. The
node set is the set of destinations the proxy saw, so a blind component contributes none of its
destinations, and the fraction described a truncated population under the name of the whole one.

Both figures now carry an **observability block**: how many components the capture layer could
see, how many completed calls and produced nothing observable while being expected to egress, and
how many are silent by design. We publish it as counts rather than names because our disclosure
rules forbid naming a measured component in published output.

### 3.6 The remedy, and what it does not cover

`NODE_USE_ENV_PROXY=1`, with a runtime new enough to implement it. Both now live in the image
definition, together with a build-time assertion that fails the image build on an older runtime.
That assertion is not defensive programming. An older Node accepts the variable, ignores it, and
produces a capture indistinguishable from a correct one, which is the same failure mode one layer
down.

It covers global `fetch` and `undici`. It does **not** cover a client using Node's `https` module
directly, one constructing its own agent, or one pinning certificates. We therefore do not claim
the blind spot is closed. We claim it is measured, and the packet capture remains the instrument
of record for what is still invisible: any SYN to a destination that is not the proxy is traffic
we are not reading.

### 3.7 The general form

An environment-variable proxy does not observe a process. It observes the subset of that process's
clients which opted in, and the composition of that subset is a property of every dependency in
the tree, including ones introduced by a transitive upgrade after the measurement was designed.
The subset cannot be enumerated in advance, and its size is not knowable from inside the
measurement, because the evidence that a client opted out is the absence of evidence.

This is why transparent interception, a redirect at the network layer, or instrumentation at the
TLS library itself, is a requirement for this class of measurement rather than an engineering
preference. Those approaches do not ask the client anything.

### 3.8 The consequence for the reader

If you are measuring an agent's egress with an environment-variable proxy, your figures describe a
subset of unknown size, and the components most likely to be missing are the ones built on modern
runtimes. That is not a caveat to add to a limitations section. It changes what your numbers are
about.

The cheapest way to find out how large your subset is does not require changing your capture at
all: run a packet capture alongside it and count outbound SYNs by destination. Every connection to
somewhere that is not your proxy is traffic your instrument is not reading. We found ours by doing
this, after the measurement had already produced two publishable-looking figures.
