# The gate

Seven conditions a run must pass before any number from it is reported. The gate is on the first
screen on purpose: it is where credibility is won or lost.

1. **Reproducible.** Two runs over the same corpus and the same pinned servers produce the same
   numbers, and the measurement core produces byte-identical artifacts, demonstrated, not
   asserted. `make verify` proves the core (tests/test_reproducibility.py). A capture run adds
   network non-determinism; pin server versions by digest so the controllable part stays fixed.

2. **A command behind every number.** Each of the six has a `make` target and an `aggregate`
   subcommand (rule 6). A figure with no command does not ship.

3. **No names in aggregate output.** No server id, host, or tool name in anything published.
   Counts, ratios, and category breakdowns only. Enforced by test
   (tests/test_aggregate.py::test_aggregate_output_leaks_no_server_names).

4. **No content stored.** Only salted digests and references. Raw payloads exist in memory during
   the hashing pass and nowhere else. `.gitignore` refuses to track runs at all as a backstop.

5. **Nothing runs outside the container, no real credentials.** The harness runs in Docker with a
   throwaway network. Servers that need a token are launched without one; we watch the attempt,
   we never hand a real secret to a server under test.

6. **Threats to validity written, at least four.** See docs/THREATS.md. A measurement that does
   not state how it could be wrong is not a measurement.

7. **Responsible disclosure.** If a server egresses to a destination its documentation does not
   declare, stop and flag it. Publish nothing that locates that specific server until the finding
   is authorized. Aggregate first, name never (see rule 3).
