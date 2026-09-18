# Threats to validity

A measurement that does not state how it could be wrong is not a measurement. At least four,
gate rule 6. Each names the threat and what it does to the numbers.

1. **The corpus biases what is observed.** We drive a fixed set of tool calls. A server only
   egresses in response to what we call, so the fan-out we see is the fan-out of our corpus, not
   the server's full behavior. Mitigation, now done rather than planned: every corpus is written
   against the server's real `tools/list` output, committed under `registry/probes/`, and
   `tests/test_corpus_matches_probes.py` fails if an argument stops validating against the real
   `inputSchema`. The corpus SHA is in the manifest, so the input is pinned to the output.

   What that fixed, stated plainly because it was live: the corpus previously named tools that
   do not exist. Of four names guessed for `everything`, three were wrong. Each would have
   returned an error, recorded zero egress, and biased numbers 1, 2 and 5 downward with nothing
   in the output distinguishing "this server does not egress" from "we called a tool that is not
   there". Any number produced before this alignment should be discarded, not adjusted.

   The residual threat is unchanged and unfixable by alignment: we drive read-only tools only, so
   a server whose egress happens on a write path is measured on the wrong path. That is a
   deliberate bound -- driving writes would make the harness act on the operator's tree and on
   real third parties -- and it is a floor on the numbers, not a correction to them.

2. **A sandbox run observes one execution, not the behavior.** Deadbugz served its malicious tool
   description only from the fourth request onward. A single pass can miss time-gated or
   count-gated behavior. Mitigation: repeat runs, vary order, and treat any number as "observed in
   these runs", never "always".

3. **A server that detects the sandbox does nothing.** A server that fingerprints the container,
   the proxy CA, or the absence of a real TTY can suppress its egress and look clean. This biases
   every number downward. It is unfixable in a sandbox and is stated, not hidden. eBPF SSL uprobes
   (docs/METHOD.md) reduce the proxy-detection surface but not the sandbox-detection surface.

4. **The most-installed do not represent the long tail.** Ten popular servers are curated,
   audited, and unrepresentative of the thousands of small servers where supply-chain risk
   concentrates. The numbers describe the head of the distribution. The tail is future work and is
   labeled as such.

5. **Absent credentials change behavior.** Servers that need a token are run without one and fail
   auth. A failed call may egress less (or differently) than a successful one. We measure the
   attempt, which is honest for destination and argument-forwarding, but the fan-out of a fully
   authenticated session can be larger. Stated.

6. **Proxy blind spots undercount fan-out.** The terminating proxy reads only HTTP(S) it can
   decrypt. Non-HTTP protocols and certificate-pinned clients bypass it, so numbers 1 and 2 are
   lower bounds. The pcap backstop records the connections the proxy missed; until reconciliation
   is implemented, treat the proxy fan-out as a floor.

7. **Sequential-driving attribution.** Number 5's ground truth relies on driving one call at a
   time, so exactly one call is active per server. This is correct for the measurement and is the
   point (it lets us measure content-match recall against ground truth), but it means the harness
   does not itself exercise the concurrent case that makes attribution hard in production. Number 5
   estimates how well content matching would do there; it does not reproduce there.

8. **One of the ten servers cannot be measured without credentials, and three are abandoned.**
   Probed 2026-09-18, each pinned to the exact version in `registry/servers.yaml`. This is what
   the sweep actually found, and it is not the clean ten the registry implied.

   Nine of ten started with no credentials at all and answered `tools/list`: everything (13
   tools), filesystem (14), memory (9), sequential-thinking (1), git (12), time (2), fetch (1),
   puppeteer (7), github (26), and brave-search (2) only with a placeholder key. 87 tools in all.

   On naming servers here, since gate rule 3 says no server id "in anything published". Rule 3's
   subject is aggregate output -- the numbers artifact -- and that is where the enforcing test
   sits (tests/test_aggregate.py). This section is a threats-to-validity statement about which
   servers could be measured at all, drawn from public registry metadata that
   `registry/servers.yaml` already commits, and it names no capture finding. Rule 7, the one that
   forbids locating a server, governs a server caught egressing somewhere undeclared, and nothing
   here is that. The counts above are checked against `registry/probes/` by
   `tests/test_corpus_matches_probes.py`, per gate rule 2: no figure without a command behind it.

   **brave-search did not start.** It exits before the JSON-RPC handshake on all four candidate
   protocol revisions with `BRAVE_API_KEY environment variable is required`. This contradicts the
   reasoning `registry/servers.yaml` was built on, that a credential-less server "will fail auth,
   but the connection attempt still reveals the destination host": there is no connection attempt,
   because the process is gone before it speaks. So the harness measures nothing at all for
   brave-search, rather than measuring a failed call. Its two tool schemas were recovered with
   `BRAVE_API_KEY` set to a placeholder string, which is enough to keep its corpus schema-checked
   but does NOT make it drivable. Effect on representativeness: the egress-bearing half of the
   registry is four servers and only three of them can be driven, so every per-server egress
   number rests on three observations. Number 3 in particular (fraction of servers that propagate
   `traceparent`) has a denominator small enough that one server changes the answer visibly.

   **Three of the ten are abandoned upstream**, which sharpens threat 4 rather than sitting beside
   it. brave-search: last npm release 2024-12-04, marked deprecated on the registry, moved out of
   the reference server set. github: last release 2025-04-08, deprecated, superseded by GitHub's
   own Go implementation. puppeteer: last release 2025-05-12, deprecated, removed from the
   reference set. Threat 4 says the popular head is curated and audited and therefore
   unrepresentative of the long tail. The measured version is worse: three of the ten servers in
   this curated head are not maintained at all. They still install, and github and puppeteer still
   run, which is exactly why they stay in the registry -- an abandoned server that people still
   install is a more honest sample of real exposure than a fresh one. But their behavior is frozen
   at a date, so a number that depends on them describes 2024 and 2025 code, not current practice,
   and it will not track whatever the maintained servers do next.

   **A fourth finding, about the protocol rather than the servers.** github, puppeteer and
   brave-search accept an `initialize` announcing `2025-11-25` and answer `2024-11-05`. They are
   lenient: they accept a revision they do not implement instead of rejecting it. So a harness
   cannot learn a server's real revision by seeing its own choice accepted, which is why the probe
   stores what we sent and what the server answered as two separate fields. It is also why
   `2026-07-28` was removed from the candidate ladder in `harness/probe.py`: these three would
   have accepted that too, and the registry would have recorded a revision nobody speaks.

9. **Nothing here has been driven under capture yet.** Everything above comes from `initialize`
   plus `tools/list`, which is the probe, not the measurement. The probe never calls a tool, so it
   produces no egress and therefore no fan-out. The alignment makes a future run countable; it
   does not itself count anything. No number in `docs/THE-SIX-NUMBERS.md` has a measured value as
   of this writing, and an aligned corpus must not be mistaken for a result.
