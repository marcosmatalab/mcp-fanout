# The six numbers

Each number has one definition, one thing it decides, and one command that measures it (rule 6).
Numbers 1 to 4 are the paper. Number 5 is the viability. Number 6 sizes the recursion.

The commands read the latest run under `runs/`. Build a run with `make run` (real capture) or
`make selftest` (synthetic, no Docker), then run `make numbers` or an individual `make n<N>`.

## Two blocks of metrics, and what each block may conclude

The figures divide into two blocks that answer different questions and must not be mixed in one
claim.

**Instrument block. Bench only (phase A, `docs/PHASES.md`), where ground truth is known because
we built the servers and the destinations.**

| Metric | Question |
| --- | --- |
| Capture recall | of the transfers we caused on purpose, what fraction did the sensor see |
| Attribution precision | of the strong attributions claimed, what fraction were correct |
| False provenance matches | how often material was claimed present that was not ours |

These cannot be computed against real servers at all: recall needs a denominator of known
transfers, and precision needs a known cause. Quoting a recall figure from a phase B run would be
quoting a number with no denominator.

**Phenomenon block. Real servers (phase B).**

| Metric | Number |
| --- | --- |
| Egress per invocation, p50 / p95 / max | 1 |
| Distinct domains per invocation | 2 |
| `traceparent` propagation, segmented by answered revision | 3 |
| Provenance coverage | 4 |
| Attribution grade distribution | 5 |
| Self-hostable fraction of touched destinations | 6 |

**No means.** Every per-call distribution reports p50, p95 and max, and no mean. The mean
misleads on exactly these shapes: the first real capture had one call at 89 connections and one
at 2, giving a mean of 45.5, a figure no call produced. Percentiles are computed by nearest rank,
never interpolated, so every published figure is a value some call actually produced. Reporting
the mean alongside was rejected: a single number always ends up quoted alone.

**Deliberately out of scope for now: CPU and latency overhead.** It is an MVP measurement and it
decides nothing about whether the phenomenon is real or whether attribution works. Measuring it
here would spend bench time on a figure that cannot change the architecture decision.

## Number 1: outbound connections per tool call, in three figures

**Definition.** For each driven tool call, three distributions over all calls including those
that produced zero egress, each reported as **n, p50, p95 and max**. **They are published
together, always.**

| Figure | What it counts |
| --- | --- |
| `connections_raw` | every observed connection, unfiltered |
| `distinct_hosts` | distinct destination hosts per call (the same quantity as number 2) |
| `connections_excluding_package_infrastructure` | raw minus connections to hosts on the declared list |

**Why three and not one.** One figure is misleading, and the first real capture proved it rather
than suggested it. `mcp-server-fetch` opened 87 connections to `registry.npmjs.org` while serving
a single `fetch` call, because it installs an npm package at tool-call time. That gives a raw mean
of 45.5 connections per call. The number is true and it answers the wrong question: those 87 are
serial connections to one host of package infrastructure during a known, single active call, so
they are trivially attributable. What this number exists to decide -- whether the causal union is
the product or a footnote -- turns on **concurrent connections to distinct domains**, and by that
measure the same call has 2. Publishing 45.5 on its own would be a false headline built from a
true count.

**The raw figure is never discarded and never filtered.** A server with genuine fan-out to a host
that happens to be on the exclusion list stays completely visible in `connections_raw`. The
excluded figure is an additional view, never a replacement.

**The exclusion list is declared, not a silent filter.** It lives in
`registry/package-infrastructure.json`: committed, versioned by date, and containing only hosts
whose sole purpose is distributing software packages. The aggregate output cites it by
`list_name`, `version` and `sha256`, so any reader can check exactly which list produced the
figure. The citation deliberately contains **no hostnames**, because gate rule 3 forbids a host in
published output; the committed file plus the published digest is what makes the list auditable
without naming anything in the aggregate. General-purpose CDNs are deliberately excluded from the
list (`storage.googleapis.com`, where puppeteer fetches Chromium, is not on it) because they also
carry ordinary application traffic and listing them would hide real egress.

If the list cannot be loaded, the third figure is reported as `null` with the reason named. It is
never computed against an empty list, because "no list loaded" and "no package traffic" would then
produce identical output and only one of them is a finding.

**Decides.** Whether the causal union is trivial or is the product. If distinct hosts per call is
1 (a server calls its own API and stops), attribution is trivial and the product is Half B alone.
If it is large with concurrency, the union is the whole product.

**Command.** `make n1` (`aggregate --number 1`).

**Caveat.** The proxy sees HTTP(S) it can terminate. Non-HTTP or certificate-pinned flows are a
lower bound here and are caught by the pcap backstop (harness/run.sh); this number is therefore
a floor, stated as a floor.

## Number 2: distinct domains per tool call

**Definition.** Per call, the count of distinct destination hostnames among its outbound
connections. Reported as a distribution (n, p50, p95, max).

**Decides.** The size of the publishable finding. Domain sequences alone leak information (the
local-research-agent study measured 64 to 155 distinct domains per query and recovered most of
the prompt's functional intent from the domain sequence alone). A large distinct-domain count is
the headline.

**Command.** `make n2`.

## Number 3: fraction of servers that propagate `traceparent`

**Definition.** Of the servers driven, the fraction for which at least one outbound request
carried the exact W3C `traceparent` we set in `params._meta` (SEP-414), **segmented by the
protocol revision the server answered with**, plus the pooled figure.

**Why segmented.** SEP-414 is a minor change of the **2026-07-28** revision. A server that
answers `2024-11-05` predates the convention being written down, so "it does not propagate" is a
fact about its age, not about the convention's uptake. Pooling distorts in both directions: it
understates uptake among servers that could have implemented it, and it implies the older ones
declined something that did not yet exist. The pooled figure is still published, because
withholding it would be its own distortion, but the segments are the answer. Servers whose
answered revision is unknown get their own bucket; "not known" is not a revision.

**Decides.** Whether the cooperative path is worth anything today. If near zero **among servers
on a revision that documents it**, an instrumented server is rare and the observational approach
is the only one that works against real servers.

**Command.** `make n3`.

## The two matched channels (numbers 4 and 5)

Numbers 4 and 5 both rest on literal matching, and both match **two channels, counted
separately**:

- the **request target**: the path plus query string, exactly as it goes on the wire;
- the **body**: the request payload.

This is a change of definition, made deliberately and recorded here rather than slipped in.
Until it was made, only the body was matched. A secret in a query string has already left the
machine -- it is bytes on the wire toward a third party -- so excluding it was not the
digest-only policy, it was a blind spot covering the entire GET channel, which is the channel
most third-party APIs use and the one the incidents this project cites travel on. With body-only
matching, numbers 4 and 5 were structurally zero for every GET-based server, and the first real
capture of `fetch` demonstrated exactly that: the canary rode in the URL, was on the wire, and
the flow recorded no provenance at all (under the single-column model then in force it scored
`DECLARADO`, which is the conflation the evidence model later replaced).

Three constraints on how it is done, each of which is a correctness requirement, not a style
choice:

1. **The target, never the absolute URL.** The scheme and host are not content drawn from our
   context. Including them would manufacture self-matches (a context file that mentions a
   hostname would "match" every request to that host) while telling us nothing about what left.
2. **The two channels are never pooled into one figure.** Number 4 reports
   `target_matched_bytes` and `body_matched_bytes`; number 5 reports `efectivo_by_channel`.
   A causal match in a query string and one in a request body are both literal evidence, but
   they are not the same claim, and a single combined figure is indistinguishable from one
   inflated with URLs. Totals are given too, labelled as totals.
3. **Matching stays byte-literal, so it stays digest-only.** The target is shingled and hashed
   exactly like the body; only salted digests are persisted. Nothing about the privacy model
   changes. What changed is the definition of the two numbers, which is why it is written here.

Residual limit, in the same direction as before: a value the client percent-encodes, base64s, or
splits across parameters is not detected in the target. That is a false negative, the safe side.

## Number 4: provenance coverage

**Definition.** Two of the three evidence claims (`docs/DOCTRINE.md`, the evidence model),
reported together because neither means anything alone:

- **occurrence**: how many flows were `observed` (TLS terminated, request read) versus
  `connection_only`. A provenance figure is meaningless without knowing how many requests could
  be read at all.
- **provenance**: how many flows carried `none` / `context` / `arguments` / `both` / `unknown`
  recognisable material of ours, plus the number of bytes covered (exactly, by k-gram interval
  union) by any session context file, **per channel** (target and body) with the total.

The third claim, attribution, is number 5's and is never joined to these in one sentence.

**Decides.** Whether content matching has signal at all. If nothing from the context ever leaves,
Half B has no measurable base.

**Command.** `make n4`.

**Method.** Exact k-gram coverage, not winnowed. See `src/mcpfanout/match.py`
(`match_request`, renamed from `match_body` when the name stopped being true). A match shorter
than k = 16 bytes is not counted, which is the safe direction (under-count, never over-count).

## Number 5: distribution of attribution grades

**Definition.** Of all outbound connections, the count in each attribution grade:
`TRACE_PROPAGATED`, `CONTENT_UNIQUE`, `CONTENT_AMBIGUOUS`, `CONTENT_MATCH_UNCONTESTED`,
`TEMPORAL_ONLY`, `UNATTRIBUTED`. Defined in `docs/DOCTRINE.md`, the evidence model. Reported with
the named reason for each grade, the channel split of content matches, and the declared exclusion
list that graded eligibility, cited by name, version and digest.

**Strong attribution counts `TRACE_PROPAGATED` and `CONTENT_UNIQUE` only.**
`CONTENT_MATCH_UNCONTESTED` is deliberately excluded: a match with one call in flight
discriminated nothing.

**There is no single "causally unifiable" fraction any more.** That figure was the old `EFECTIVO`
share, and under sequential driving it counted every content match as strong evidence when
nothing had been told apart. It is replaced by the full distribution, which cannot be quoted as
one flattering ratio.

**What it cannot decide yet, and the output says so.** The number emits `sequential_driving:
true` while every flow was seen with at most one call in flight. While that holds,
`CONTENT_UNIQUE` is unreachable by construction and the strong-attribution figure must not be
read as an answer to whether content matching recovers attribution where time cannot. That is
phase C's question (`docs/PHASES.md`), and the tautology it avoids is written out in
`docs/DOCTRINE.md`.

**Decides.** Whether the whole product works, once phase C exists. This is the number nobody has
measured.

**Command.** `make n5`.

**Honest denominator.** An argument-less call ("list my files") has nothing to match and falls to
`TEMPORAL_ONLY` or `UNATTRIBUTED` by construction. That split is itself a publishable result: the
attributable share depends on tool type, and the breakdown is reported rather than a single ratio.

## Number 6: fraction of touched third parties that are self-hostable

**Definition.** Of the distinct destination nodes touched in the run, the fraction that are
themselves self-hostable (local or a self-hostable MCP node), versus remote leaves.

**Decides.** How far the edge observer can advance before the chain breaks (docs/METHOD.md, the
recursion). A shallow self-hostable interior means the recursion buys nothing and the break point
is always the first hop; a deep one makes the recursion critical infrastructure.

**Command.** `make n6`.

**Conservative rule.** An unknown public domain counts as a remote leaf. Claiming self-hostability
we do not have would inflate the recursion's reach, so unknown counts against it. The breakdown is
reported so the unknown share is visible and can be curated down (registry/selfhostable.json).
