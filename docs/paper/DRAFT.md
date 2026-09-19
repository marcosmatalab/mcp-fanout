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
at all, because Node.js ignores those variables in its global `fetch` unless a flag that is off by
default is explicitly enabled.

We measure whether an agent's outbound requests can be attributed to the tool call that caused
them, across **ten of the most-installed Model Context Protocol servers, driven under packet and
proxy capture with 130 tool calls in concurrent waves of 2, 5 and 10, plus a 26-call sequential
pass**. Ten curated servers are the head of a distribution whose tail is where small,
unaudited implementations live, and every figure below describes that head. Matching is
byte-literal over structural tokens, with no content retained and no inference. Against a
threshold of 0.80 fixed and cryptographically sealed before any measurement existed, the
attributable share of call-caused, content-eligible flows is **0.6579**. The instrument does not
meet its own bar, and we report that rather than the two higher figures the same question yielded
while the instrument was blind: 0.8947 and 0.8095. Every fix to the instrument's observability
lowered the headline.

Separately and with the same matcher, **no fragment of any planted context file ever appeared in
a request toward a third party**: zero matched bytes across every flow of every run. The servers
we measured forward what a call gives them and not what is sitting in the session around it.

The corrected instrument then found two behaviours in the measured environment, both disclosed to
their maintainers before publication: a tool call that downloads and executes **41 third-party
packages** while it runs, from unpinned version ranges with no lockfile, in **82 registry requests
one day and 87 the day before**, which is the instability rather than a stale figure; and a server
whose embedded browser reaches destinations the server's own documentation does not declare.

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

The total is the second, independent check, and it rules out the obvious alternative reading. It
rises from 140 to 150: also exactly ten. One hop became two, client-to-API replaced by
client-to-proxy plus proxy-to-API, so the connection count grows by exactly the number of
connections that changed shape. Had the fix instead provoked new traffic, retries, a different
code path, a second client waking up, the total would have moved by some other amount. It did
not.

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

---

## 4. Method

### 4.1 Four constraints, and what each one costs

The design is fixed by four prohibitions, adopted before any code and never relaxed. Each is
stated with the capability it gives up, because a constraint whose cost is not named is a
limitation discovered late and presented as a principle.

**Never inject.** Nothing is planted inside a third party: no marker, no token, no identifier
smuggled into a call toward someone else's system. The observer lives at our own edge. *Cost:* we
cannot follow a value once a third party re-emits it. A marker that travelled the chain would
answer questions we cannot, and it would be an attack surface, a terms-of-service problem, and a
data-minimisation problem at once.

**Never store content.** Only salted digests and references survive memory. The single sentence
the collector may emit is "the fragment with hash X, from reference Y, appeared in output toward
domain Z." *Cost:* a match cannot be inspected after the fact, only recomputed, and that cost is
load-bearing later in this paper.

**Never infer.** Byte-literal matching only: no paraphrase detection, no semantic propagation, no
model in the loop guessing what a server forwarded. *Cost:* a server that re-encodes a value
before sending it is a miss. We take the miss. A false negative understates our own result, which
is the safe direction; a false positive would manufacture evidence, which is not.

**Never act.** Observe and record. Do not block, redact in flight, alter, or intervene. *Cost:*
nothing this system produces prevents anything. It is evidence, not enforcement, and the
distinction shapes everything above it.

A boundary is needed between the third constraint and ordinary parsing, because our matcher
decomposes structure. Splitting a URL per RFC 3986, percent-decoding, and walking a JSON document
to its scalar leaves are permitted: each recovers a structure the sender put there, by a published
algorithm. Case folding, stemming, edit distance, synonym expansion and embeddings are not. The
test is not whether a step improves recall. It is whether two independent implementations of the
written rule must agree on every input. Percent-decoding must. Stemming need not.

### 4.2 Two instruments, because there are two questions

We report two quantities that had shared one matcher, and separating them is the central design
change of this work.

**Did a request carry material from the session's context?** The material is prose: documents,
notes, configuration sitting in the agent's working set. A literal k-gram is the right instrument,
and its false-positive rate on our negative control is zero.

**Was a request caused by a specific tool call?** The material is not prose. It is JSON fields
whose values reappear on the wire as path segments and query parameters. The correspondence is
structural, and a k-gram cannot see it.

The diagnosis is one line of data. At k = 22 bytes, a request for `/docs/deploy/runbook` (20
bytes) is invisible and `/docs/deploy/checklist` (22 bytes) is not. Sensitivity that depends on
how a documentation site happened to name a page is measuring the site. On realistic argument
material the k-gram matcher found only 0.5385 of the calls that had literally caused the requests
in front of it.

So the provenance question keeps the k-gram and the attribution question moves to **structural
containment**: decompose both the call's arguments and the request into the same vocabulary of
tokens, and attribute when every token of the call is present in the request. Containment rather
than intersection, because intersection fires whenever a call shares one token with a request, and
for a hostname that is every request to that host. Containment needs no score and no threshold,
which is why the criterion has no tunable constant.

Nothing crosses in plaintext. The driver decomposes arguments in its own process and publishes a
keyed digest per token; the capture layer decomposes the wire and digests what it finds; the
comparison is set containment over digests.

### 4.3 Discrimination, and why one token is never enough

Containment alone attributes too much. In a wave of ten concurrent calls, one call was
`{"url": "https://example.net/", "max_length": 2000}`, whose only structural token is the
hostname. It is contained in every request of its own wave, including ten `robots.txt` fetches the
client emits before each retrieval.

We therefore require that a candidate call own at least one token that distinguishes it from the
other calls in flight. This is a principle rather than a threshold: a call that owns nothing its
neighbours do not own leaves the candidate set, instead of making the whole wave ambiguous.

The measured justification, over one wave of twenty flows:

| rule | strongest grade awarded | of which wrong |
|---|---|---|
| containment alone | 20 | **9** |
| ambiguity floor over the whole wave | 9 | 0 |
| **discrimination as a principle** | **17** | **0** |

Nine of twenty confident, wrong attributions, every one of them a constant client-emitted path
credited to whichever call happened to own a single generic token. The middle rule is safe and
discards two thirds of what containment gained. We adopt the third, with an additional floor: a
single structural token never earns the strongest grade, because one token identifies a class and
not a call.

The rule has a cost we report rather than discover: a call whose tokens are a proper subset of a
concurrent call's is also excluded, and loses the attribution of its own request. Section 5.5
returns to this, because it is a limit of the method and not of our implementation.

### 4.4 Pre-registration, and a prediction of ours that was false

Every figure in section 5 was predicted before the code that produces it existed. The predictions,
their falsification conditions, and the verdict threshold live in a block whose SHA-256 is asserted
by a test, so editing a word after the fact fails the suite. The denominator the verdict binds to
is a committed file whose own hash is quoted inside the sealed block, so a later entry cannot
quietly move what the threshold is measured against. Held-out corpora are retired once measured
and replaced rather than reused.

One further rule governs the instrument itself, and it earned its place by being violated four
times: **every instrument needs a test that fails when the instrument is absent, not only when it
is wrong.** A wrong number gets investigated; a green gets published. Our four instances were an
addon that failed to load and produced an empty, clean-looking run; a constant that diverged and
silently stopped matching; a self-test that serialised a field it never populated; and a published
artifact that omitted the very denominator its verdict is measured against. The class is that an
absent input yields a well-formed output, and well-formed output is what gets reviewed.

**One of our sealed predictions was false.** We predicted the pre-registered run could be
re-graded without re-capturing. It cannot: the stored records predate the fields the new matcher
writes, so that run is not re-gradable from what was persisted. The prediction is still in the
seal, unedited, with the correction beside it and the digest proving the original was not touched.
We keep it there deliberately. A pre-registration in which every prediction held is evidence that
the predictions were written to be safe.

The failure is also a result. "Re-gradable from what was persisted" is the question an auditor
asks first, and the general answer is that adding a field to an evidence record makes every
earlier record un-re-gradable under the new rule. That is a property of evidence systems that
evolve, not of this one.

**What the apparatus does not establish.** We pushed the sealed block to an external host only
after measuring. A commit's author date is local metadata, so an external clock witnesses that the
bundle existed by a certain instant and fixes nothing about the order within it. Two disclosure
issues filed on a third party's infrastructure carry server-set timestamps that corroborate the
content, which is narrower than corroborating the order. The rule we derive, and state here rather
than in a limitations section: **seal, commit, push, and only then measure.** A seal that has not
left the machine is a draft with a hash on it.

---

## 5. Results

### 5.1 The honesty curve

We measured the same quantity three times, each time after repairing something the instrument
could not see.

| # | what the instrument could not see | components with observed egress | denominator | attributable share |
|---|---|---|---|---|
| 1 | its own records, and Node's global `fetch` | 2 | 19 | 0.8947 |
| 2 | Node's global `fetch` | 2 | 21 | 0.8095 |
| 3 | nothing we have found; see 3.6 | **3** | **38** | **0.6579** |

Every repair lowered the headline. That direction is the result, not the individual points: **a
measurement whose headline improves as its instrument improves is measuring the instrument.** Ours
did the opposite, which is the only shape consistent with the earlier figures having been
optimistic for reasons unrelated to the matcher.

We do not claim the curve has stopped. It falls as blindness is removed, and the packet capture is
the only thing that says whether blindness remains. A fourth point below 0.6579 is the expected
shape if another non-cooperating client is found, not a surprise.

### 5.2 The figure, and the threshold it does not meet

Of 38 call-caused flows eligible for content attribution, **25 are attributed to exactly one tool
call**: 0.6579, against a pre-registered threshold of 0.80.

The instrument does not meet its bar. We publish three denominators together and never one alone:

| denominator | what it counts | share |
|---|---|---|
| all flows (140) | everything the capture saw | 0.1786 |
| call-caused and eligible (57) | excludes package-manager traffic and pre-launch flows | 0.4386 |
| **content-eligible (38)** | **also excludes client-constant targets** | **0.6579** |

The first is not comparable with the others and is marked as such wherever it appears. It is
published because discarding it would hide how much of a run is machinery: 83 of 140 flows were a
package manager, and 19 more were targets a client emits identically whatever the call asked for,
such as `robots.txt` before every retrieval. The third is the one the verdict binds to, and the
list defining it was frozen by hash before the measurement.

**On the two figures in this paper that look contradictory, and are not.** Section 5.6 reports 16
flows carrying recognisable argument material; this section reports 31 flows matched structurally.
They are different instruments answering different questions by design (4.2), and the gap is the
size of what the k-gram cannot see: a structural token shorter than 22 bytes. The k-gram figure is
byte-identical to the one we published before this work, which is how we verify the separation
held. Reporting a single reconciled number here would hide the only direct measurement we have of
what changing instruments bought.

### 5.3 Where the thirteen missing attributions went

| cause | count |
|---|---|
| single-token floor | **6** |
| contained but not discriminating | 5 |
| never contained | 2 |

Every one of the six is on the component that became visible only after the instrument was fixed.
Its arguments are single free-text queries. This is not a coincidence, and 5.4 is the reason.

### 5.4 What content attribution is for: a claim about the shape of arguments

> **Content attribution works on tools whose arguments carry structure, and does not work on tools
> whose arguments are free text. No matching rule changes this without manufacturing false
> attributions.**

`{"query": "modelcontextprotocol servers"}` is 29 bytes and **one** structural token.
`{"query": "logs"}` is four bytes and **one** structural token. The rule treats them identically,
because what it measures is how many independent structural commitments a call makes, and both
make one.

The evidence runs both ways. Where arguments are URLs, attribution is near-total: 15 of 17 on one
component, the two misses being subset re-reads rather than shape (5.5), and on a second component
both of the requests its calls actually caused, its two remaining flows being its embedded
browser's own background traffic rather than anything a call asked for. Where arguments are free
text, 6 of 17 could not rise above ambiguous. And the price of relaxing the
rule is measured, not assumed: permitting a single token to earn the strongest grade produced nine
false attributions in twenty flows (4.3).

**A reader can apply this to their own deployment without running anything.** Take each tool's
schema and ask what its arguments decompose into: a hostname, path segments, query values, JSON
string leaves. Four or five tokens means its calls are attributable under concurrency. One token
means they are not, and no configuration will change that. This is the opposite of what a
demonstration on URL-shaped tools would suggest, which is why we state it as a claim rather than
as an explanation of our own shortfall.

It is a claim about the content channel alone. A propagated trace context attributes a free-text
call exactly, which is what 5.6 measures.

### 5.5 A limit in the method, not in the implementation

If one call's structural tokens are a proper subset of a concurrent call's, then every request
containing the second call's tokens also contains the first's. No implementation of containment
can separate them: it follows from subset being transitive over one vocabulary, not from how
candidates are scored or ties broken. A rule may lose the subset call or guess. There is no third
option inside the method.

The case is not pathological. It is an agent re-reading its own document with more precision: the
same page with a section anchor, a line range, a filter, a page number. We measured it as
`/docs/deploy/runbook` losing its own request to `/docs/deploy/runbook?section=rollback-steps` at
ten concurrent calls, and attributing cleanly at two and at five, where the superset call was not
in flight. The loss is created by concurrency, not by the call.

A lost call of this kind is indistinguishable, in a grade distribution, from a request that never
matched. We therefore publish the count of calls excluded for owning no distinguishing token as a
figure in its own right. Without it the limit is invisible in the output and reads as a weak
matcher.

### 5.6 The other two numbers, and the one that is zero

**Context leakage: zero.** Planted context files sat in the agent's working directory throughout
every run, carrying unique tokens that exist nowhere else. Not one byte of them appeared in any
request toward any third party: zero matched bytes, zero flows, across every run. Sixteen flows
carried recognisable material from a call's own arguments, which is forwarding what the call
supplied. None carried material from the session around it. This is the most reassuring result
here and the one a reader of a paper titled *measuring tool-call provenance* is entitled to expect
in the abstract, so it is there.

**Trace-context propagation: zero of three.** No component that we could observe propagated our
trace context into its outbound requests. The denominator is three, not ten, and the difference is
section 3: a component whose traffic never reached the proxy did not decline to propagate
anything. We report the all-components figure beside it, marked not comparable, because
suppressing it would hide how much of the set was invisible.

Zero of three is a small denominator and we do not dress it up. What it establishes is that the
mechanism which would attribute free-text calls exactly, and which 5.4 identifies as the only
thing that can, is not in use by anything we were able to watch.
