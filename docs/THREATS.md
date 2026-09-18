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

10. **A tool call is not atomic: `mcp-server-fetch` reaches a package registry mid-call.** Named
    as a finding rather than filed as noise, because it is the most interesting thing the first
    capture produced.

    Measured 2026-09-18 against `mcp-server-fetch@2026.8.18` (PyPI), launched via `uvx`, driven
    under capture with the two-call corpus in `corpus/calls/fetch.json`. Serving those two calls,
    the server opened **87 connections to `registry.npmjs.org`** and 4 to the requested host. The
    npm connections are not our package manager: the uv and npm caches are warmed before the
    proxy starts (`harness/run.sh`), and they appear *after* the tool call's own request, on the
    first call only. The server shells out to npm **during** `tools/call`. The same behavior is
    visible from the other side: it writes npm's output to its own stdout, corrupting the
    JSON-RPC channel with lines like `added 41 packages, and audited 42 packages in 4s`.

    Why this is supply-chain surface and not a curiosity. A tool call that installs a package
    while it runs can receive **different code on different calls**, from a registry that is not
    the one the server itself was pinned from. Pinning `mcp-server-fetch@2026.8.18` pins the
    Python distribution and says nothing about the npm package resolved at call time. Everything
    this project pins -- the exact version in `registry/servers.yaml`, the corpus digest in the
    manifest -- describes the state before the call, and this server mutates its own
    implementation after that snapshot is taken. There is no version in our records for the code
    that actually ran.

    What it does to the numbers, and how that is handled. Number 1 publishes three figures
    together (raw connections, distinct hosts, and raw excluding the declared list in
    `registry/package-infrastructure.json`), because a single figure here is true and misleading
    at once: those 87 are serial connections to one infrastructure host during a known call, so
    they are trivially attributable and say nothing about whether the causal union is hard. For
    this run the three read, as p50 / p95 / max: raw 2 / 89 / 89, distinct hosts 1 / 2 / 2, and
    excluding package infrastructure 2 / 2 / 2, with `package_infrastructure_connections` = 87.
    The raw figure is never discarded, so this server's 87 connections stay visible in it, which
    is how a reader finds this threat from the numbers alone.

    Number 5 grades all 87 as `UNATTRIBUTED` with the reason *ineligible: package infrastructure
    traffic, carries no tool-call arguments*, alongside 3 `TEMPORAL_ONLY` and 1
    `CONTENT_MATCH_UNCONTESTED`, for a strong-attribution fraction of 0.0. Under the previous
    single-column model this same run read as 90 `DECLARADO` and an `EFECTIVO` fraction of 0.011,
    which asserted temporal correlation for 87 flows that cannot carry an argument at all. See
    `docs/DOCTRINE.md`, the evidence model, and `docs/THE-SIX-NUMBERS.md`, numbers 1 and 5.

    Not generalised from one server. Whether other servers install at call time is unmeasured;
    this says only that one of the ten does, and that the raw-versus-excluded gap is where to
    look for the rest.

    Provenance of the figures above, and how the tension that used to sit here was resolved.
    They come from run `20260918T200935Z`, a single-server capture driven with `--only fetch`.
    Its **normalized aggregate is committed** at `docs/figures/20260918T200935Z.json`, and the
    command that regenerates it is recorded inside that file. So every figure quoted above is
    re-derivable from this repository alone, and `tests/test_committed_figures.py` fails if this
    prose and that artifact drift apart.

    Earlier this paragraph said the opposite, and the reason is worth keeping. Gate rule 2 wants
    a command behind every number, gate rule 4 refuses to track runs, and the two together made a
    quoted figure measured but unverifiable. The way out was not to relax either rule but to
    notice they govern different objects: the AGGREGATE is counts and category breakdowns with no
    host, no server id and no payload digest, while the RUN holds per-flow records and salted
    digests tied to specific servers. Committing the first satisfies rule 2; not committing the
    second satisfies rules 3 and 4. See `docs/THE-GATE.md`, rules 1 and 4.

11. **The canary is only detectable where the client does not re-encode it.** Numbers 4 and 5
    match the request target and the body byte-literally (`docs/THE-SIX-NUMBERS.md`, "The two
    matched channels"). A value the server percent-encodes, base64s, splits across parameters, or
    puts in a header we do not match is a false negative: the flow grades `TEMPORAL_ONLY` when it
    was causally ours. Every such miss pushes the attributable share **down**, so the published
    distribution is a floor, not an estimate. The first `fetch` capture produced exactly one flow
    of 91 with a content match, through the target channel, and under sequential driving it grades
    `CONTENT_MATCH_UNCONTESTED` rather than `CONTENT_UNIQUE` (`docs/DOCTRINE.md`, the evidence
    model). That is a floor over a two-call corpus in which one call carried a canary, and it is
    not an estimate of what the technique achieves at scale.

