# The gate

Nine conditions a run must pass before any number from it is reported. The gate is on the first
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

   **THE DECISION PROCEDURE, in three branches.** The rule used to say "if a server egresses
   somewhere its documentation does not declare", and that sentence does not decide the commonest
   case, which is a package manager downloading a dependency. So:

   1. **Contacted by the launcher before the server process starts.** Not the server's egress. It is
      recorded apart and triggers no disclosure. Mechanically: the flow was seen in a pre-first-call
      phase (`record.PHASES_NOT_CALL_CAUSED`), the launch command is a package launcher
      (`disclosure.PACKAGE_LAUNCHERS`, from the declaration's `launch_tool`), and the destination is
      on the declared list in `registry/package-infrastructure.json`. **All three**, each from
      declared data: none of them is inferred from how a hostname looks.
   2. **A direct consequence of a corpus call, to a destination the server's documentation names.**
      Declared behaviour. Published as such, no disclosure.
   3. **Anything else.** Gate rule 7 fires. Stop, and say so before publishing anything from that
      run. This includes pre-first-call egress that is NOT a package registry, which is a launched
      process reaching somewhere on its own at startup, and it includes a call-caused destination the
      documentation does not name.

   The branches are applied by `make disclosure`, and the third one is the only one that produces
   `review_required`. What the command still does not do is decide branch 2 for you: whether the
   documentation names a destination is read by a person, once, for the hosts the check lists.

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

9. **The matcher is calibrated on real language before volume is measured.** No figure from a
   real-server run may be published until the matcher's false-positive rate on structured language
   has been measured and published, with its interval, over at least 200 concurrent call pairs that
   share language structure and no information. See `docs/CALIBRATION.md`; the command is
   `make fp`.

   Why this is a separate rule from rule 8, when both are about the instrument. Rule 8 asks whether
   the sensor SEES what it should and whether it CLAIMS only what it can support, and it was
   satisfied against keyed digests: forty bytes of material that exists nowhere else. That is the
   most favourable input the matcher will ever get. Rule 9 asks a question those fragments cannot
   answer at all: on natural language and URLs that share a JSON envelope, a path prefix, a host
   and ordinary English words, how often does the matcher affirm a coincidence that does not exist?
   Without that figure, the error bar on every volume number is unknown in the one direction that
   inflates it, and "the margin is tiny" is an adjective.

   The rule includes its own anti-tuning clause, because the corpus that produces the number is
   also the corpus any improvement is developed against. The corpus is split in two halves before
   any measurement exists: one for calibration, one reserved and measured once at the end, which is
   the half the published figure comes from. `calibrate.load_negative` refuses the reserved half to
   a calibration purpose, and tests fail if that refusal is bypassed or if the halves stop being
   independent.

10. **Every instrument needs a test that fails when the instrument is ABSENT, not only when it is
    wrong.** No figure from an instrument may be published until a test exists that goes red if
    that instrument silently does nothing.

    This is a gate rather than a style note because it is the failure mode this repository keeps
    producing, and because of what it does to the process rather than to the code: a wrong number
    gets investigated, and **a green gets published**. An absent instrument is not a bug that
    announces itself. It produces a clean run, a passing suite and an empty result that reads as a
    finding.

    **The class is established by five instances, not argued from one.**

    - `capture_addon.py` used a relative import. mitmproxy loads an addon by path under a synthetic
      package name, so the import raised, mitmdump logged it and carried on proxying. The run
      completed, the suite was green, and `flows.jsonl` was empty, which reads exactly like a
      server that egressed nothing. Guarded now by `tests/test_capture_addon_loads.py`, which loads
      the file the way mitmproxy does.
    - The addon carried its own `k = 16` after `calibrate.choose_k` moved the shipped constant to
      22. A k mismatch does not error. It just stops matching, so the capture graded at a k no
      published figure describes and nothing anywhere went red. Caught only because a fixture's own
      token came back non-causal.
    - `make selftest` serialised the structural fields and never populated one of them, because its
      synthetic path does not run the addon's request hook. A passing selftest was fully consistent
      with a capture layer that never called the structural matcher at all. Caught by writing the
      test in this rule, not by the suite.
    - `make figures` wrote `content_denominator: null` into every committed artifact, because
      `compute_all` was called without the constant-path list. The published artifact omitted the
      quantity the published verdict is measured against, and it validated, diffed and committed
      cleanly.
    - `README.md` stated a compute cost, a reproducibility guarantee and a version number that the
      measurements contradicted, and went on doing so for four days after each was disproved. It is
      the page almost every reader sees, and nothing in the suite could tell that a sentence of
      prose had stopped being true. Five instances is not an anecdote: the class is that an ABSENT
      input produces a WELL-FORMED output, and well-formed output is what gets reviewed. The fifth
      extends it past code: a document is an artifact, and a published artifact that omits or
      contradicts the result it is measured against fails at the one job it has.

    **What the test has to do, since "we have tests" is what was true in all three cases.** It must
    exercise the instrument's real entry point, with the real loader where there is one, and it
    must assert a POSITIVE result that only a working instrument can produce. Asserting that a
    field is present is not enough: all three instances above had their fields present. Assert that
    the field holds the value the instrument was supposed to compute.

    **Applied to itself.** A detector whose job is to find something must be shown to find a planted
    instance of that something, in the same run, through the same code path. A scanner that has
    silently stopped scanning reports a clean result, which is this rule's own failure mode turned
    on the rule. `tests/test_credentials_never_persisted.py` does this: it plants a canary and
    fails if its own scanner misses it, before it reports that the artifacts are clean.
