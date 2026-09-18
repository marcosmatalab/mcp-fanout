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

## Number 4: outbound bytes that literally match context files

**Definition.** Across all observed outbound bodies, the number of bytes covered (exactly, by
k-gram interval union) by any session context file, and the count of flows with at least one
context match.

**Decides.** Whether content matching has signal at all. If nothing from the context ever leaves,
Half B has no measurable base.

**Command.** `make n4`.

**Method.** Exact k-gram coverage, not winnowed. See `src/mcpfanout/match.py`. A match shorter
than k = 16 bytes is not counted, which is the safe direction (under-count, never over-count).

## Number 5: fraction of connections causally unifiable by content match

**Definition.** Of all outbound connections, the fraction classified `EFECTIVO`, that is, whose
payload contains a literal fragment of the causing call's arguments. Reported with the full
state distribution (`EFECTIVO` / `DECLARADO` / `INDETERMINADO`).

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
