# Stop criteria

When to stop spending on the measurement. The measurement is one afternoon and about 10 EUR of
compute; these criteria say when that afternoon has answered the question.

## Stop, small problem

If the median fan-out (number 1) is 1 and literal coincidence (numbers 4 and 5) is zero, the idea
is real but the problem is small: servers call their own API and nothing of the context leaves.
This is knowable for about 10 EUR and an afternoon. The causal union is trivial, the product (if
any) is Half B alone, and there is no headline. Write it up and stop.

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
