# Draft. All ten sections. `OUTLINE.md` is kept as the record of structural decisions.

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
them, across **ten widely used, version-pinned Model Context Protocol servers, driven under
packet and proxy capture with 130 tool calls in concurrent waves of 2, 5 and 10, plus a 26-call
sequential pass**. These are curated, well-maintained servers and they are the head of a
distribution whose tail is where small, unaudited implementations live; every figure below
describes that head. We make no claim about install rank, which we did not measure. Matching is
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
3. **A claim a reader can apply without running anything**, with a first measurement of how much
   it bites: attribution works on a call committing two or more structural tokens and fails on one
   committing a single token, under any rule that does not manufacture false attributions. Over 87
   probed tool schemas, at most 38% are attributable from the schema alone, 22% never can be, and
   40% are undecided until a value is seen. The 38% is a ceiling: a schema declares a value's
   shape and not its entropy. We give the measured price of relaxing the rule, and the
   procedure for classifying a tool inventory without capturing anything.
4. **A pre-registration apparatus for systems measurement**, independent of the system measured: a
   digest-sealed prediction block, a verdict whose denominator is frozen by hash, held-out corpora
   that are retired once measured, and a rule that every instrument carry a test which fails when
   the instrument is absent rather than merely wrong. One of our own sealed predictions turned out
   to be false. It is still in the seal, uncorrected, with the correction beside it.

---

## 2. Introduction: what an agent's egress is, and why nobody has the number

An autonomous agent calls tools. Each call may cause the tool to reach a third party, and the
agent's operator is accountable for what leaves the machine, not for what the agent intended. The
question this paper measures is whether those two things can be connected after the fact: given a
request observed leaving a host, can it be tied to the tool call that caused it?

The question has a practical shape. An incident review asks which call sent a value to a
destination. A data-protection assessment asks which categories of data leave and under whose
instruction. A procurement review asks what a tool actually contacts, as opposed to what its
documentation says it contacts. All three need attribution of an outbound request to a specific
call, and none of them is served by a list of destinations.

The environment we measure is the Model Context Protocol, because it is where the question is
currently concrete: an MCP server is a separate process, launched by the agent's runtime, speaking
a documented protocol, and free to reach anything it likes while serving a call. MCP is the first
environment here and not the category. The unit of the design is an agent's action and its
egress, so a second environment is an adapter rather than a rewrite, and we take care throughout
to state results in those terms.

**Why the number does not already exist.** Attribution is not a property one can read off a
capture. It requires knowing what each call contained at the moment it was in flight, which means
instrumenting the caller as well as the wire; it requires a matching rule whose false-positive
rate has been measured rather than assumed, because a rule that attributes generously produces
confident nonsense; and it requires concurrency, because with one call in flight every match is
trivially unique and the figure restates the experimental setup. Work on MCP to date catalogues
destinations and permissions. We found none that reports an attributable share under concurrency
with a calibrated matcher.

**What this paper reports, in order of how much we think it matters.**

The first result is about the instrument, and it is why section 3 comes before the method. A
proxy configured through environment variables does not observe an agent's egress; it observes
the clients that chose to honour a convention, and the subset is not knowable in advance. We found
this after the measurement had already produced two publishable-looking figures.

The second is the attribution figure itself, which does not meet the threshold we fixed before
measuring, and the decomposition of why it does not.

The third is a claim a reader can apply to their own tool inventory from schemas alone, without
running anything: content attribution works on structured arguments and fails on free text.

The fourth is methodological and independent of MCP: an apparatus for pre-registering systems
measurements, including what it cost us when one of our own sealed predictions turned out to be
false.

We also report two behaviours of the measured environment, disclosed to their maintainers before
publication, in section 6. They are the most quotable material here and the least central to the
argument, and we have placed them accordingly.

**What we do not claim.** We do not claim a security result: nothing here is a vulnerability, and
the two disclosed behaviours are documented or deliberate on their authors' part. We do not claim
generality beyond the head of the server distribution we sampled. And we do not claim the
instrument is now complete; section 3.6 states precisely what it still cannot see.

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

The 38 content-eligible flows resolve as follows. Counts are FLOWS, one per outbound request,
and the three components are distinguished throughout because two of them happen to contribute 17
flows each.

| component | content-eligible flows | attributed uniquely | ambiguous, single token | no candidate |
|---|---|---|---|---|
| A, retrieval, URL arguments | 17 | **15** | 0 | 2 |
| B, API client, mixed arguments | 17 | **8** | **6** | 3 |
| C, browser driver | 4 | **2** | 0 | 2 |
| **total** | **38** | **25** | **6** | **7** |

So the thirteen that are not attributed uniquely are 6 held at ambiguous by the single-token
floor, 5 contained but not discriminating, and 2 that were never contained at all, the last being
the browser's own background traffic rather than anything a call asked for.

Every one of the six is on component B, and B is also where 8 of the 25 successful attributions
come from. The split is inside one component, not between components, which is what 5.4 is
about.

### 5.4 What content attribution is for: a claim about the shape of arguments

> **Content attribution works on a call whose arguments commit two or more structural tokens, and
> fails on a call that commits one. No matching rule changes this without manufacturing false
> attributions.**

The determinant is the token count, not the tool's category, and stating it as a claim about
*search tools* would have been wrong. `{"query": "modelcontextprotocol servers"}` is 29 bytes and
**one** token. `{"query": "logs"}` is four bytes and **one** token. But
`{"q": "tools/call repo:modelcontextprotocol/servers"}` is also a free-text search, and it
decomposes into **two** tokens because the qualifier contains a slash. The rule counts independent
structural commitments, and it does not care what the field is named.

**The evidence is inside one component, which removes the obvious confound.** Component B in 5.3
drove two families of tool against the same API in the same waves:

| tool family driven on component B | argument keys | flows | attributed uniquely |
|---|---|---|---|
| repository reads | `owner`, `repo`, `path`, `state` | 3 | **3** |
| search whose query embeds a `repo:owner/name` qualifier | `q` | 5 | **5** |
| search whose query is a bare phrase | `query` | 6 | **0** |

Same component, same credential, same concurrency, same matcher. What separates the last row from
the first two is how many structural tokens the argument value commits. A claim about components
or about tool categories would not have survived this table; a claim about argument shape does.

Where arguments are URLs throughout, attribution is near-total: 15 of 17 flows on component A, the
two misses being subset re-reads rather than shape (5.5). And the price of relaxing the rule is
measured, not assumed: permitting a single token to earn the strongest grade produced nine false
attributions in twenty flows (4.3).

#### 5.4.1 How much of a real tool surface is affected

The claim is only useful if a reader can apply it before installing anything, so we measured the
distribution over every tool schema we probed. The rule is derived from the committed
`inputSchema` and from no value: a REQUIRED property of type string commits at least one
structural token whatever the caller passes. We deliberately do not guess from a property's name
or description that it holds a URL, because suggestion is inference and this paper forbids
inference in the matcher; a schema that DECLARES `format: uri` is counted, because that is the
author stating it in machine-readable form.

**N = 87 tools across 10 servers**, every one probed and committed:

| class | tools | share | meaning |
|---|---|---|---|
| **structured**: two or more required string properties | **33** | **0.379** | at least two tokens committed by the schema itself, whatever the values. Attributable under concurrency |
| **single value**: exactly one required string property | **35** | **0.402** | one token committed. Attributable only if that value itself decomposes, which the schema cannot say |
| **no string input**: none required | **19** | **0.218** | nothing committed, so no content attribution is possible under any rule |

Read it as a lower bound and an upper bound rather than a prediction. **At most 38% of this tool
surface is attributable from its schemas alone**, before any value is seen, and the paragraph
below explains why that is a ceiling rather than a floor. **At most 78% can ever be attributable
at all**, because 22% commits no structural token whatever the caller passes. The 40% in the middle is genuinely undecided
by a schema and is decided by what callers actually pass: component B's two search families sit in
that class and landed on opposite sides of it.

We report the middle class as undecided rather than assuming it fails. Assuming it fails would
have produced a more dramatic number and a less honest one.

**And the 38% is optimistic, by a route a schema cannot see.** The rule counts structural
COMMITMENTS, not their specificity. `{"locale": "en-US", "text": "..."}` declares two required
string properties and lands in the structured class, but `en-US` discriminates nothing: it is one
of a handful of values every call to that tool will draw from, so the call effectively commits one
distinguishing token and not two. A schema declares the SHAPE of a value and not its entropy, and
no amount of reading schemas recovers the difference.

Part of this is visible and we measured it: of the 33 tools in the structured class, **1 declares
one of its required string properties as an `enum`**, with three permitted values. That single
instance is itself a lower bound on the problem rather than a measure of it, because a
low-entropy field is under no obligation to declare an enum. A status, a locale, a region code or
a two-letter language is low-entropy whether or not its author wrote the constraint down, and
those are invisible to this classification by construction.

So 38% is an upper bound on the lower bound: at most 38% of this surface is attributable from
schemas alone, and the true figure is lower by however many structured tools commit a token that
identifies a class rather than an instance. Settling that needs values, which is the same thing
the undecided middle class needs, and it is the same day of call logs that would settle both.

**The procedure for a reader**, which needs no capture and no code from us: take each tool's
schema, count its required string properties, and read off which of the three classes it is in.
Two or more means its calls are attributable under concurrency. Zero means they never are. One
means it depends on what your agent actually passes, and you can settle it by looking at a day of
your own call logs.

This is a claim about the content channel alone. A propagated trace context attributes a
single-token call exactly, which is what 5.6 measures.

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

---

## 6. Two behaviours of the measured environment

Reported here because the corrected instrument found them, and kept short because they are not
this paper's argument. Both were disclosed to their maintainers, with a stated publication window,
before this text existed. Neither is framed as a vulnerability and neither was treated as one.

### 6.1 A tool call that installs and executes third-party code while it runs

One component is a Python package that retrieves a URL and converts HTML to text. Serving a call,
it opened **82 connections to a package registry** against 4 to the host the call had named. The
package caches are warmed before the capture starts, so these are not our own installer.

The chain, read from the installed package rather than inferred from a hostname: the component
depends on a library whose HTML-conversion path checks for a `node_modules` directory and, finding
none, calls a helper that runs `npm install` in the library's own directory. That directory ships
a manifest with **no lockfile** and three dependencies declared as open-ended ranges. The install
pulls **41 packages**, and the subprocess output is not captured, so the package manager's
progress lines are written to the component's standard output, which is the protocol channel.

The property that matters is not the volume. It is that **the code executed is resolved at the
moment of the call**. Pinning the component pins the Python distribution and says nothing about
the JavaScript that runs inside it. Our own records make this concrete: the same pinned component,
driven through the same harness, produced **87 registry requests on one day and 82 on each of two
runs the next**. Two runs agreeing on 82 rules out noise, and the difference from 87 is the
instability measured rather than described. There is no version in our records for the code that
actually ran.

Disclosed as two separate reports, because there are two different asks and a single text would
let each maintainer read it as the other's problem: a lockfile, captured subprocess output and an
opt-out for the library that performs the install; a documentation note and an egress-allowlist
consequence for the component that takes the dependency.

### 6.2 A component that egresses because of what it embeds

A second component drives a headless browser. During a single navigation call it reached two
destinations its documentation does not mention. Rather than diagnose this from the hostnames, we
ran a control: the same browser binary, the same flags, the same proxy, with no MCP server in the
process tree, navigating to the same URL. The control reproduced both destinations.

So the finding is not that the component egresses somewhere undeclared. It is that **the
component's egress is not the component's**, and the difference is only visible with a control
that removes the component and keeps everything else. We report this as a method note as much as a
finding: a destination attributed to a server on the strength of a time window and a hostname can
belong to something the server merely contains.

---

## 7. Threats to validity

Ranked, not listed. The ranking is itself a result, because we got it wrong: for most of this
work we attributed a gap in our numbers to sampling, and the cause was the instrument.

### 7.1 Instrument limits, which bound everything else

**Non-cooperating clients (section 3).** Interception by environment variable is opt-in by the
observed. One of three egressing components was invisible until repaired, and we cannot prove
none remain. The packet capture bounds this: any connection to a destination that is not the
proxy is traffic we are not reading. This threat dominates because it does not degrade a figure,
it silently redefines the population.

**Protocols and encryption the proxy cannot read.** Non-HTTP traffic and certificate-pinned
clients bypass a terminating proxy entirely. Our fan-out counts are floors.

**Evidence that cannot be re-derived.** Records written before a matcher's fields existed cannot
be re-graded under it. This bit us directly: the run our threshold was pre-registered against is
not re-gradable from what was persisted, and the figure for it had to be derived from the corpus
with a published cross-check. We state it as general: **adding a field to an evidence record makes
every earlier record un-re-gradable under the new rule.**

### 7.2 Sampling, which we over-blamed

**Ten curated servers are the head of a distribution.** The tail, where small and unaudited
implementations live, is where supply-chain risk concentrates and is not sampled here.

**Absent credentials change behaviour.** Components requiring a token were mostly driven without
one. A failed call egresses less than a successful one. We credentialed one component to test
exactly this, and the result was instructive in an unexpected way: it changed no published number
while the instrument was blind, and changed the headline figure substantially once it was not.

**Our corpus is ours.** We wrote the arguments and chose the concurrency levels. Section 5.4's
claim about argument shape is the part of this paper most exposed to that choice, and it is the
part we would most want replicated on somebody else's tool inventory.

### 7.3 Method limits, which are honest and bounded

**Subset calls cannot be uniquely attributed (5.5).** A limit of containment, not of our code.

**Re-encoding defeats byte-literal matching.** A component that transforms a value before sending
it is a miss, by design. Misses understate our result.

**No ground truth on real servers.** Attribution precision has a denominator only on a controlled
bench where we caused every transfer. On real components we measure how grades are distributed,
not whether a given attribution was correct.

### 7.4 The ranking error itself

For most of this work, the gap between what we expected to attribute and what we did was
attributed to the two sampling threats above: uncredentialed components, and a curated sample. Both
were real and neither was the cause. The cause was an instrument that could not see a third of the
components that egressed at all, and it was invisible precisely because a blind component and a
silent component produce identical records.

We keep this in the paper because the reasoning error is more transferable than the finding.

---

## 8. What would change the answer

Three things, in order of how much they would move the number.

**Interception that does not ask the client.** A redirect at the network layer, or instrumentation
at the TLS library, removes the opt-in on which section 3 turns. Everything in section 5 is a
lower bound until this exists, and we do not know by how much. This is the single change that
would most alter the result, and it is the one whose effect we can least predict.

**Trace-context propagation.** A propagated context attributes a call exactly, including the
free-text calls that section 5.4 shows content matching cannot reach. **Zero of the three
components we could observe propagate one.** The mechanism is standardised, cheap, and in use
nowhere we could watch, so the ceiling described in 5.4 is a property of current implementations
rather than of the problem. Of everything in this paper, this is the recommendation we would most
like acted on: it converts the unattributable class into the attributable one without any of the
matching machinery here.

**A larger estimate of the argument-shape distribution.** Section 5.4.1 gives a first one: over
87 probed tools, at most 38% are attributable from their schemas alone, 22% never can be, and 40%
are undecided until a value is seen. Both the ceiling and the undecided middle are resolved by the
same input, a day of real call logs, which is the cheapest next measurement in this paper. That distribution, not our attribution figure, is what determines
the attributable share of any specific deployment, and ours is a small N drawn from the head of
the distribution (7.2).

Extending it is unusually cheap, which is why we single it out. It needs no capture, no proxy and
no credentials: the classification reads committed tool schemas and counts required string
properties, and it runs against any registry of MCP servers as it stands. The two obvious
extensions are breadth, several hundred servers from a public registry rather than ten curated
ones, and resolving the undecided middle, which needs one day of a real deployment's call logs
rather than its schemas. We expect the tail to be worse than the head here: small servers tend to
expose one broad tool with one free-text argument, which is the shape that does not attribute.

Two things we deliberately did not pursue, recorded so their absence is not mistaken for an
oversight: a per-request candidate rule that would recover some lost attributions, which we
predict reintroduces the false attributions of 4.3 and have declared as an amendment to be
measured afterwards; and weighting a token by improbability rather than counting tokens, declared
after seeing the failure and therefore unable to replace the figure it would improve.

---

## 9. Reproducibility

Every figure in this paper has a command, and the commands are in the repository rather than in
this text. The cited object is the repository itself, at a tagged release with a DOI, including
its signed history and the sealed pre-registration block.

**What is committed:** the normalized aggregates of each run, which are counts, ratios and
category breakdowns with no hostname, no component identifier, no tool name and no payload digest;
the corpora, pinned by content hash in each run's manifest; the registries that define every
exclusion, each cited in the output by name, version and SHA-256; and the test suite, including the
tests that fail when an instrument is absent.

**What is not committed, and why:** the runs. A run holds per-flow records and salted digests tied
to specific components, so committing one would both name components and ship digests our own
constraints forbid publishing. The aggregate is committed instead, which resolves the tension
between "a figure must be re-derivable from the repository" and "a run must not be tracked".

**Reproducing a figure exactly** requires re-running the capture, which contacts live third
parties and will not reproduce byte for byte: the measured environment changes between days, which
is itself one of our findings (6.1). What reproduces exactly is the normalized aggregate of a
given run, the calibration figures, and every derived quantity in sections 4 and 5.

**The honest gap.** Runs captured before the structural matcher existed are not re-gradable under
it (7.1). The three points of the honesty curve therefore come from three runs and not from three
gradings of one, and the first is derived from the corpus with its cross-check against the real
run published alongside it.

---

## 10. Conclusion

The instrument does not meet its bar. On the head of a real tool distribution, with a matcher
calibrated on real language and a threshold fixed before any measurement existed, 0.6579 of
content-eligible outbound flows could be attributed to the single tool call that caused them,
against a pre-registered 0.80.

The product question this measurement was built to answer is not answered, and was deliberately
never frozen. That refusal is inside the sealed block, so it could not be replaced by a verdict
once a result existed.

What we would carry away is not the figure.

**Content attribution is a capability over the structured part of a tool surface, not over the
surface.** A deployment can know in advance which part that is, from schemas alone, before
installing anything. The free-text remainder is not attributable by content under any rule that
does not manufacture false attributions, and the mechanism that would attribute it exactly is
standardised, cheap, and in use by none of the components we could observe.

**And the reasoning error, which generalises past this paper.** When a measurement shows less than
expected, the first hypothesis reached for is sampling: the sample was too small, too curated, too
constrained. Those hypotheses were available, plausible, true as statements, and not the cause.
The cause was that the instrument could not see a third of what it was pointed at, and it was
invisible because an instrument that sees nothing and a subject that does nothing produce the same
record. We reached for sampling first, and we were wrong for longer than we should have been.

The discipline that eventually caught it was not cleverness. It was a second instrument that did
not depend on the first one's cooperation, and a rule that every instrument carry a test which
fails when the instrument is absent rather than merely wrong. We wrote that rule after being
caught three times. It caught the fourth.
