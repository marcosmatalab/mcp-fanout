# Stop criteria

When to stop spending on the measurement, where "spending" turned out to mean attention rather than money.

**Corrected 2026-09-20.** Earlier versions of this paragraph said "one afternoon and about
10 EUR of compute". Both figures were guesses and both were wrong, and README.md now publishes
the measured table that disproves them. Measured: **0 EUR** of cloud compute, because everything
runs in Docker on one machine; **0 EUR** of paid APIs, the only credential being a free-tier
GitHub token; **138 seconds** of actual driving across 21 capture runs; **two days** of wall
clock. The money cost is genuinely zero and the real cost is attention.

These criteria say when the measurement has answered the question.

The pre-registered version of this, with the sensor and product gates beside it, is
`docs/PHASES.md`. This file is the reasoning; that file is the commitment made before the data
existed. Two additions there that are not below, because they are not technical outcomes and
decide the same thing anyway: a target market of hosted remote MCP, which this method cannot
observe at all, and buyers who consider their existing gateway sufficient.

## Stop, small problem

If the median fan-out (number 1) is 1 and literal coincidence (numbers 4 and 5) is zero, the idea
is real but the problem is small: servers call their own API and nothing of the context leaves.
This is knowable at the cost stated above, which is two days of attention and no money. The
causal union is trivial, the product (if any) is Half B alone, and there is no headline. Write it
up and stop.

**This is the branch that fired.** Number 1's median is 0 and number 4 is zero bytes. What the
criterion did not anticipate is that the instrument would fail its own threshold on the way
(`docs/PREREG-F2.md` section 16), so "write it up and stop" is being followed with a negative
result about the apparatus rather than a small result about the phenomenon.

## Continue, there is a product

If the median fan-out is greater than 1, or literal coincidence appears with files a user would
not expect to leave (a `.env`, a config, an internal note), there is both a product and a
headline. The causal union becomes real work and number 5 is the viability signal. Proceed to the
architecture decision (recursion vs single-hop, docs/METHOD.md), now with the number in hand.

## Stop and disclose, always

Independent of the two above: if any server egresses to a destination its documentation does not
declare, stop the run and follow docs/THE-GATE.md rule 7. A surprising destination is a finding to
be handled responsibly before it is a data point.

## What the measurement does not decide

- Whether this sells on its own or is again a fine feature inside someone else's product. The
  number does not answer that, but without the number the question cannot even be posed.
- The Zscaler CTPH patent (US20210374121A1), which must be read in full before any commercial use.
- Which part of the chain runs on our own machine, which sets the ceiling on the product's value.
