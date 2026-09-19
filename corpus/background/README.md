# The background corpus, and why it is FOUND material plus one half of the negative corpus

F1.3 weights each k-gram by how common it is, which means something has to define "common". That
something is this background corpus, and how it is built decides whether the resulting figure means
anything at all.

## The construction rule

`sources.json` names the documents. Two groups, and neither was written for this experiment:

1. **Found API material already in the repository**: the committed tool schemas under
   `registry/probes/` (real `tools/list` output from ten real servers) and both driving corpora
   (`corpus/calls/`, `corpus/concurrent/`). Thirty-one documents of genuine API-shaped JSON and
   realistic agent arguments, authored for other purposes.
2. **The CALIBRATION half of the negative corpus**, and only that half. It is tuning material by
   definition, so using it to learn what boilerplate looks like is exactly what it is for.

## Why the calibration half is in it, and why that is not cheating

The published figure is measured on the **held-out** half. The two halves share **no information**
(`tests/test_negative_corpus.py` fails otherwise, in both directions, over the whole byte content of
every call), so nothing this background knows about the held-out half's payloads can have come from
here. What can cross from one half to the other is **structure**: the JSON envelopes, the path
prefixes, the locale enum, the ordinary English. That is precisely the thing rarity weighting claims
to be able to suppress, so letting it learn structure from the tuning half and then testing it on the
reserved half is a fair test of the claim rather than a rigged one.

The alternative was to hand-author a background containing exactly the literal runs the negative
families declare as shared. That would guarantee the rate falls and would measure nothing: it is
fitting the mechanism to the test set with extra steps.

## What this background is NOT

**It is not large, and document frequency over 32 documents is a coarse proxy for "common in the
world".** A production deployment would build this from its own traffic, where a JSON envelope seen
in ten thousand requests gets a weight that reflects it. Thirty-two documents can say "this run of
bytes appears in most of what we have seen" and nothing stronger, and the figure in
`docs/CALIBRATION.md` is bounded by that.

**It is not independent of the author.** The same person wrote the negative corpus and chose these
sources. The genuinely independent test is a background built from real traffic, which this project
does not have, and that limit is stated in the F1.3 section rather than implied away.
