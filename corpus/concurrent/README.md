# The concurrent-pass corpus

One file per server, same shape as `corpus/calls/` (a list of `{tool, arguments, why}`), driven as
**waves of N concurrent calls** instead of one call at a time. `harness/drive_all.py --mode
concurrent` reads it; `registry/servers.yaml` names it per server in `concurrent_corpus_ref` and
caps N in `max_concurrency`.

## The one design rule, and why it is the opposite of the bench's

The phase A bench requires that **no two fragments share a 16-byte run**
(`tests/test_bench_metrics.py` fails otherwise), because a bench whose fragments collide measures
its own collisions instead of the sensor's discrimination.

This corpus requires the opposite, and for the same reason turned around: **arguments must look
like what a real agent would send, which means they share structure.** Common words, the same
domain, the same path prefix, the same parameter names. If the arguments were made artificially
distinct, the concurrent pass would replicate the bench on a real server and measure something
already known. What is unknown is whether content matching still discriminates when the material
is natural language and URLs rather than keyed digests, and that is only askable if the material
is realistic.

`tests/test_concurrent_corpus.py` enforces both halves of this: every argument validates against
the server's real schema (as for the sequential corpus), and the corpus must NOT be pairwise
k-gram-disjoint, which is the mechanical form of "not artificially distinct".

## No canary here, deliberately

`corpus/calls/` plants `CANARY_QRY_ab12cd34ef56789a0b1c2d` in the arguments of every egress-capable server,
because the sequential pass asks whether recognisable material of ours travels at all. Planting
the **same** marker in N concurrent calls would make every flow match every call, so every grade
would be `CONTENT_AMBIGUOUS` by construction: our marker, not the servers' behaviour. Planting a
**unique** marker per call would be the bench again.

So the concurrent pass matches on the real argument text, which is the material a production
agent would actually be carrying. The cost is stated: less material is byte-literally matchable,
so this pass sees fewer content matches than the sequential one. That is the measurement, not a
defect of it.
