# The gate

Eight conditions a run must pass before any number from it is reported. The gate is on the first
screen on purpose: it is where credibility is won or lost.

1. **Reproducible, at two levels.** The levels are different because the things being reproduced
   are different, and demanding one standard for both produced a rule that failed for the wrong
   reason.

   **Level 1, byte for byte: the measurement core and normalized artifacts.** Two runs over the
   same input produce byte-identical output. Proved, not asserted, by `make verify`
   (`tests/test_reproducibility.py`).

   **Level 2, normalized result: a capture run.** Two captures of the same pinned servers must
   agree on the NORMALIZED result: the same destinations or destination categories, the same
   logical graph, the same provenance sources, the same distribution of attribution grades, and
   figures within declared tolerances. They must NOT be expected to agree byte for byte.
   Timestamps, traceparents, nonces, socket order and DNS answers all differ between captures,
   so a byte-for-byte rule over a capture fails on clerical noise while saying nothing about
   whether the phenomenon reproduced. It would be a rule that fails for the wrong reason, which
   is worse than no rule because it trains everyone to ignore it.

   A capture's normalized aggregate is committed as an artifact so the figures quoted from it
   are re-derivable; see rule 4 for why that does not conflict with never committing a run.

2. **A command behind every number.** Each of the six has a `make` target and an `aggregate`
   subcommand (rule 6). A figure with no command does not ship.

3. **No names in aggregate output.** No server id, host, or tool name in anything published.
   Counts, ratios, and category breakdowns only. Enforced by test
   (tests/test_aggregate.py::test_aggregate_output_leaks_no_server_names).

4. **No content stored, and no run committed.** Only salted digests and references. Raw payloads
   exist in memory during the hashing pass and nowhere else. `.gitignore` refuses to track
   `runs/` at all as a backstop.

   What rule 1 permits, and why it does not conflict: the NORMALIZED AGGREGATE of a capture may
   be committed under `docs/figures/`. It is counts, ratios and category breakdowns with no
   hostname, no server id, no tool name and no digest, and it is what the aggregate command
   already emits. It is not the run: the run holds per-flow records and salted digests tied to
   specific servers, and that is what must never be tracked. Committing the aggregate is what
   makes a quoted figure re-derivable, which rule 6 asks for; committing the run would break
   this rule and rule 3 at once.

5. **Nothing runs outside the container, and lab accounts only.** The harness runs in Docker with
   a throwaway network, enforced by a check in `harness/run.sh` rather than a comment.

   "No credentials at all" was the previous rule and the probe sweep measured why it does not
   work: `brave-search` exits before the JSON-RPC handshake without `BRAVE_API_KEY`, so there is
   no failed call to observe and no connection attempt to watch. The rule produced zero data for
   the servers it was meant to cover, and it implied a safety it did not deliver either, since
   what matters is not the absence of a token but the blast radius of the one used.

   So: **lab accounts**, with every one of these properties, and a server is not measured until
   they all hold.

   - a fictitious organization, not a real one with a test project inside it
   - synthetic data only, and zero personal data of any kind
   - minimum permissions: read-only wherever the API offers it
   - revocable tokens, held outside the repository and outside the image
   - a spending limit set on the account before the first run
   - rotated at the end of the measurement, whether or not anything looked wrong

   Bait tokens in `corpus/context/` stay synthetic and unique (`CANARY_*`) and are never real
   secrets. That part of the old rule was right and is unchanged.

6. **Threats to validity written, at least four.** See docs/THREATS.md. A measurement that does
   not state how it could be wrong is not a measurement.

7. **Responsible disclosure, with a command behind it.** If a server egresses to a destination its
   documentation does not declare, stop and flag it. Publish nothing that locates that specific
   server until the finding is authorized. Aggregate first, name never (see rule 3).

   `make disclosure` (`src/mcpfanout/disclosure.py`) reduces a run's destinations to the ones
   nobody expected, per server, against the declared set in
   `registry/declared-destinations.json`, and exits non-zero if anything needs reviewing. It runs
   at the end of every capture and prints a stop banner. Until it existed, this rule was honoured
   by reading a hostname list after a run and remembering what belongs there, which works for one
   server and fails for ten, silently, in the direction of publishing.

   **What the command does not do**, because the bound matters more than the convenience: it does
   not decide the rule. The declared set is derived from the committed tool schemas and the
   packages' stated purpose, NOT from a reading of each upstream README, and the registry file says
   so in its own `_what_basis_means` field. Asserting what a document says without having read it
   is the plausible guess this project keeps finding in its own history. The command narrows a
   hostname dump to a short list of destinations to read documentation ABOUT; a person then reads
   it. Three outcomes, never two: clear, review required, and **undeterminable** when the
   declaration is missing, because unevaluated is not the same as satisfied.

   Its report names servers and hosts, so it stays in the run directory, which is gitignored, and
   never under `docs/`.

8. **The instrument passes before the phenomenon is measured.** No figure from a real-server run
   (phase B) may be published until the controlled bench (phase A) has passed the sensor gate in
   `docs/PHASES.md`: capture recall at or above 95%, zero false strong attributions, false
   provenance matches under 1%, and a reproducible normalized result.

   This is a gate and not advice because the failure it prevents is silent. A sensor that loses
   known traffic produces numbers whose error is unknown, and recall and precision cannot be
   computed against a third-party server at all: recall needs a denominator of transfers we
   caused on purpose, precision needs a known cause to check against. A phase B run therefore
   cannot tell you whether the sensor worked. Measuring the phenomenon first means finding out
   afterwards, if ever, and every figure published in between is unfalsifiable.
