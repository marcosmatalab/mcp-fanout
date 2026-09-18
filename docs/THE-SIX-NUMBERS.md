# The six numbers

Each number has one definition, one thing it decides, and one command that measures it (rule 6).
Numbers 1 to 4 are the paper. Number 5 is the viability. Number 6 sizes the recursion.

The commands read the latest run under `runs/`. Build a run with `make run` (real capture) or
`make selftest` (synthetic, no Docker), then run `make numbers` or an individual `make n<N>`.

## Number 1: outbound connections per tool call

**Definition.** For each driven tool call, the count of distinct outbound connections observed
while it was the active call. Reported as a distribution (n, mean, median, max) over all calls,
including calls that produced zero egress.

**Decides.** Whether the causal union is trivial or is the product. If the median is 1 (a server
calls its own API and stops), attribution is trivial and the product is Half B alone. If the
median is large with concurrency, the union is the whole product.

**Command.** `make n1` (`aggregate --number 1`).

**Caveat.** The proxy sees HTTP(S) it can terminate. Non-HTTP or certificate-pinned flows are a
lower bound here and are caught by the pcap backstop (harness/run.sh); this number is therefore
a floor, stated as a floor.

## Number 2: distinct domains per tool call

**Definition.** Per call, the count of distinct destination hostnames among its outbound
connections. Reported as a distribution.

**Decides.** The size of the publishable finding. Domain sequences alone leak information (the
local-research-agent study measured 64 to 155 distinct domains per query and recovered most of
the prompt's functional intent from the domain sequence alone). A large distinct-domain count is
the headline.

**Command.** `make n2`.

## Number 3: fraction of servers that propagate `traceparent`

**Definition.** Of the servers driven, the fraction for which at least one outbound request
carried the exact W3C `traceparent` we set in `params._meta` (SEP-414).

**Decides.** Whether the cooperative path is worth anything today. If near zero, an instrumented
server is rare and the observational approach is the only one that works against real servers.

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
scored `DECLARADO`.

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

## Number 4: outbound bytes that literally match context files

**Definition.** Across all observed outbound requests, the number of bytes covered (exactly, by
k-gram interval union) by any session context file, reported **per channel** (target and body)
with the total, and the count of flows with at least one context match in each channel.

**Decides.** Whether content matching has signal at all. If nothing from the context ever leaves,
Half B has no measurable base.

**Command.** `make n4`.

**Method.** Exact k-gram coverage, not winnowed. See `src/mcpfanout/match.py`
(`match_request`, renamed from `match_body` when the name stopped being true). A match shorter
than k = 16 bytes is not counted, which is the safe direction (under-count, never over-count).

## Number 5: fraction of connections causally unifiable by content match

**Definition.** Of all outbound connections, the fraction classified `EFECTIVO`, that is, whose
**request target or body** contains a literal fragment of the causing call's arguments. Reported
with the full state distribution (`EFECTIVO` / `DECLARADO` / `INDETERMINADO`) **and with
`efectivo_by_channel`**, the split of the EFECTIVO count across `target` / `body` / `both`.

The channel split is part of the definition, not decoration. An EFECTIVO share built entirely on
query strings supports a different reading than one built on request bodies, and publishing the
fraction without the split would invite exactly the objection that the number was inflated with
URLs.

**Decides.** Whether the whole product works. This is the number nobody has measured. Because the
corpus is driven sequentially, we have ground-truth attribution for every flow; number 5 measures
how often content matching ALONE would have recovered that attribution, which is exactly the case
that matters when calls are concurrent and time attribution fails.

**Command.** `make n5`.

**Honest denominator.** An argument-less call ("list my files") has nothing to match and falls to
`DECLARADO` or `INDETERMINADO` by construction. That split is itself a publishable result: the
causal-union rate depends on tool type, and we report the breakdown rather than a single flattering
ratio.

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
