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

6. **Proxy blind spots undercount fan-out, and the size of the blind spot is now measured.** The
   terminating proxy reads only HTTP(S) that is routed through it and that it can decrypt.
   Non-HTTP protocols and certificate-pinned clients bypass it, so numbers 1 and 2 are lower
   bounds. The pcap backstop records the connections the proxy missed; until reconciliation is
   implemented, treat the proxy fan-out as a floor.

   **Measured 2026-09-19, on the first ten-server capture: a client that does not honour the proxy
   environment is invisible to the proxy and visible only in the pcap.** The proxy is a
   `HTTP(S)_PROXY` proxy, which means interception depends on each client choosing to use it.
   Python's requests and urllib do, npm and npx do, Chromium does. Node's own `fetch` (undici) does
   **not**: it ignores `HTTP_PROXY` and `HTTPS_PROXY` by default. One of the ten servers reaches its
   API that way, so its API traffic never entered `flows.jsonl` while the tool call plainly
   succeeded and returned the API's own answer.

   The pcap is what proves it rather than a suspicion: of 53 outbound SYNs in that run, 26 went to
   the proxy on loopback and one went straight to the API's address on port 443. So for that server
   numbers 1, 2, 4 and 5 are not a floor with a small gap, they are **zero for a reason that has
   nothing to do with the server**, and no figure about it may be read from this capture layer.

   How it is handled, and what it costs. It is reported, not silently patched, because the two
   available fixes are not equivalent. Injecting a proxy agent into each server's runtime would mean
   modifying third-party code inside our own harness, which is the wrong side of negative 1 in
   spirit even where it is technically our own process. Transparent interception (a netfilter
   REDIRECT of all outbound 80/443 into mitmproxy, inside the container) is the real fix: it removes
   the dependence on client cooperation entirely and would also catch the non-HTTP and
   non-proxy-aware cases. It is a capture-layer change with its own failure modes, so it is a costed
   decision rather than a patch, and until it is taken the per-server coverage is part of the
   result: which servers were observable at all is a finding of the run.

   Two consequences to state once and not forget: a per-server figure from this layer is only
   meaningful for servers whose client honoured the proxy, and the pcap SYN count is the honest
   denominator for how much was missed.

7. **Each phase B pass can only answer half the question, and neither half may be quoted as the
   other.** Phase B is driven twice (`docs/PHASES.md`), and the split exists because a single pass
   is wrong whichever way it is driven.

   Driven **sequentially**, exactly one call is in flight per server. That is what makes numbers 1
   and 2 meaningful, because "connections per call" is a per-invocation figure and with ten calls in
   flight it would be a figure about our own wave size. But `CONTENT_UNIQUE` requires more than one
   candidate, so under this pass the strong-attribution fraction is **0.0 by construction**, for
   every server, whatever the servers do. That zero is not a finding and the aggregate says so in
   the output itself.

   Driven **concurrently**, the grade distribution becomes a measurement, and the per-call figures
   stop being readable in the same run. So numbers 1 to 4 come from one pass, number 5 from the
   other, both labelled, never merged. `harness/drive_all.py` refuses to write both into one run.

   The residual, after the split: production concurrency is not our concurrency. An agent's real
   traffic is not waves of N identical-shaped calls climbing a ladder, and phase C is where the
   pattern is adversarial rather than tidy.


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

12. **Number 5 is published as a LOWER BOUND, not as an estimate, because the sensor's self-match recall on realistic argument material is below 1: half the realistic material does not match itself.** Measured, with a
    command behind it: `make inventory`, artifact
    `docs/figures/calibration/inventory-k22.json`, and the full decomposition in
    `docs/CALIBRATION.md`, "The self-match ceiling".

    Self-match is the true-positive question in its easiest possible form: does a call's own argument
    material appear in the request that same call caused, with no competing candidate, nothing
    concurrent and no window involved. Over the negative corpus's four realistic families it is
    **0.5**, and it was already 0.5312 at the old k, so this is not a consequence of the k the sweep
    chose. A call that fails here cannot be attributed by content under any concurrency, at any
    grade.

    Why, per family and measured rather than assumed: in one family the JSON envelope never reaches
    the wire, because the server reassembles the fields into a path, so the longest run the arguments
    share with the request is a path segment of 14 to 16 bytes. In another the arguments carry spaces
    and the query string carries `+`, so the run breaks at the first space and the longest survivor
    is 7 to 13 bytes. The two remaining families self-match completely. The planted bait is not
    implicated: all five `CANARY_` values sit above both detection floors.

    **What it does to the numbers.** An attributable share measured by a sensor that cannot see half
    of the realistic material it is shown is at most half of the true share. So the attribution grade
    distribution is a floor, in the same direction as threat 11 and for a deeper reason: threat 11 is
    about a canary a client re-encodes, this is about ordinary argument material never reaching the
    wire as a literal run at all. Both push the published share down, which is the safe direction.
    Neither is fixable without inferring, which is negative 3, so both are declared rather than
    closed. `number_5`'s own output carries `published_as: lower_bound` with this reason, and a test
    fails if it stops doing so.

13. **The in-flight window is OUR declaration, not the server's concurrency.** `driver.drive_wave`
    publishes all N calls as in flight before sending any of them, and clears the set after the
    wave. So a server that internally serialises a wave of ten still has each of its flows graded
    against ten candidates, and a `CONTENT_AMBIGUOUS` at N = 10 does not say the server had ten
    things in flight. It says **the observer could not tell them apart**.

    That is the right claim for a tracer, which is why it is built this way: an observer at the edge
    knows what the client had outstanding, not what the server did internally. But it biases the
    concurrent pass **pessimistically**, which is the safe direction and is stated rather than
    corrected: discrimination is measured as harder than a server's own internals may make it.
    `grades_by_window_size` is what keeps the dependence on our wave size visible instead of pooled
    away.

    A second, smaller effect from the same mechanism: the rungs are **not independent samples**. A
    wave at N = 2 drives the first two calls of the corpus and a wave at N = 10 drives those same
    two plus eight more, deterministically, because a reproducible run cannot draw a random subset
    (gate rule 1). So the rungs share material by design, and a trend across N is a trend over
    nested sets, not over independent draws.

14. **The concurrent pass has no ground truth, so a false strong attribution in it would be
    invisible.** Precision needs a known cause, which exists only where we caused the transfer:
    phase A. There it was measured, at zero false strong attributions over 33 strong claims. In
    phase B nothing checks whether a `CONTENT_UNIQUE` was earned, and no figure from that pass may
    be read as though something did.

    Why that is acceptable here and not everywhere: the two claims are separate. "The sensor does
    not claim a cause it did not have" is an instrument property, measured on the bench and gated by
    rule 8. "How the grades are distributed over real traffic" is a phenomenon property, and it is
    what phase B measures. The reading to refuse is the one that treats a phase B strong-attribution
    count as a verified one. The pre-registered prediction in `docs/PHASES.md` names this asymmetry
    explicitly, because it is exactly the half of the prediction that the pass cannot falsify.


15. **A server that embeds a browser produces egress the server never asked for, and attributing
    it to the browser is a measurement here rather than a reading: `@modelcontextprotocol/server-puppeteer@2025.5.12`
    reached `clients2.google.com` and `accounts.google.com` during a single `puppeteer_navigate`
    call, and a bare headless Chromium launched with the same flags through the same proxy with no
    MCP server in the process tree reached both of them too.** Any MCP server embedding a browser
    engine will present the same property, whoever writes it.

    The class and the instance are published together, deliberately, and the reason is that each
    one alone is a different kind of wrong. The class alone ("browser-embedding servers carry
    background traffic") is unverifiable: nobody can check it against anything. The package alone
    reads as an accusation about code the maintainer did not write, because the traffic is
    Chromium's. The cause has to sit in the same sentence as both.

    **How it was measured, and why a control was needed at all.** Gate rule 7 flagged the two
    hosts. The obvious diagnosis was that the embedded browser checks for updates on its own, and
    an obvious diagnosis is still a guess: the same observation is equally consistent with the
    server initiating those requests. So the diagnosis was tested against its own negative. `make
    control` drives a CONTROL run (`src/mcpfanout/control.py`, `harness/control_browser.py`): the
    same browser binary the package downloaded into its own cache, the same flags the package
    passes in a container (`--no-sandbox --single-process --no-zygote`), the same proxy delivered
    the same way (HTTP(S)_PROXY in the environment, not `--proxy-server`, because a browser does
    not resolve the two identically), the same navigation target read out of
    `corpus/calls/puppeteer.json`, and no MCP server anywhere in the process tree.

    Three launches with a cold profile each, twelve seconds of dwell apiece, because the traffic
    under investigation is background traffic and a control killed at page load would miss exactly
    the class of request it exists to observe. Result: **both hosts under review reached in all
    three launches**, plus two the server's own run did not produce (`redirector.gvt1.com` and a
    `gvt1.com` edge node, which is a component download the longer dwell had time to reach). So
    `only_under_the_server` is empty: there is no destination of that server's that the bare
    browser fails to explain. Verdict `cause_reproduced`, exit 0, command and artifact in
    `docs/figures/control/20260919T125335Z-control-vs-puppeteer.json`.

    **What a reproduced control does and does not establish.** It establishes that the MCP server
    is not a NECESSARY condition for that egress: remove it and the traffic still happens. It does
    not establish that the server never initiates such a request, because no black-box observer can
    prove a negative about a process it did not write. The direction of the evidence is the
    publishable part, and the verdict string carries its own meaning inside the artifact so it
    cannot be quoted as more than it is.

    **Neither flow carried content, and that was checked rather than assumed. This is the question
    that decides what the finding IS**, because a background beacon carrying nothing is a note and
    the same host carrying a fragment of a call's arguments is the phenomenon the six numbers
    exist to measure. Both channels read zero on both hosts, and they are two different
    quantities: the ARGUMENT channel (a boolean per flow: did any k-gram of the driving call's
    arguments appear) is false on both, and the CONTEXT channel (bytes of a planted bait file
    covered) is zero bytes with `matched_refs` empty. The POST body to `accounts.google.com` was
    **1 byte**, which makes that one floor-free: there is no room in one byte for a fragment of any
    length, so it does not depend on the calibrated k at all. The GET to `clients2.google.com`
    carried 143 bytes of request target and no body, and its zero IS at k = 22
    (`docs/CALIBRATION.md`, F1.2), so what it says exactly is that nothing the sensor can see
    travelled there.

    **The control carries its own positive control, which is what makes those zeros mean
    anything.** A run in which nothing matches is evidence only if something COULD have matched.
    The control publishes the corpus call's own argument digests to the capture addon exactly as
    the driver does for a real call, so its navigation to the corpus URL should be causal, and it
    is: 3 of the control's 15 flows are causal, one per launch, all of them the navigation, and
    the remaining 12 background flows carry nothing on either channel. Without that, "the
    background requests carried nothing" and "the matcher saw nothing at all" would be the same
    observation, in the direction that flatters the diagnosis. `is_the_sensor_alive` is in the
    artifact for that reason and a test fails if threat 15 ever rests on a control whose matcher
    never fired. If a browser's background request had carried our argument material, that would be
    a far more
    serious finding than this one, and this is the measurement that would have shown it.

    **What it does to the numbers.** Nothing, and that is worth saying explicitly. These flows
    grade `UNATTRIBUTED` and count in numbers 1 and 2 as what they are: outbound connections and
    distinct domains produced while a call was in flight. They are not filtered out. A tracer whose
    honest answer is "your agent's tool call caused five connections and two of them are the
    browser's own housekeeping" is more useful than one that silently drops them, and the
    `package-infrastructure` exclusion list is deliberately not extended to cover them
    (`registry/package-infrastructure.json` says why: those are general-purpose CDNs that also
    carry ordinary application traffic).

    **Disclosure.** Raised with the maintainers as a documentation gap and not as a vulnerability:
    the tool's description says it navigates to the URL it is given and does not mention the
    background traffic an embedded browser carries, which is material to anyone deploying it where
    egress is reviewed. No severity, no identifier, no deadline. Date and text in
    `docs/DISCLOSURE-LOG.md`, and the instance is named here under the authorisation recorded
    there. Consistent with how threat 10 treats the server that shells out to npm mid-call.

16. **A match can enter numbers 4 and 5 and still be unreconstructible from the digests that were
    persisted, which is the property an external auditor presses first.** Two thresholds, and they
    are different guarantees: a shared run of at least **k = 22** bytes IS matched, because the
    numbers count exact k-grams; a run of at least **w + k - 1 = 29** bytes is also guaranteed to
    survive winnowing, which is what the digest-only fingerprints on disk keep. Between 22 and 28
    bytes a match is counted and may not be re-derivable afterwards.

    **This is measured, not feared.** `make inventory` decomposes it per family
    (`docs/figures/calibration/inventory-k22.json`, and `docs/CALIBRATION.md`, "The self-match
    ceiling"): **5 of the 8 `doc_url` calls share a run between 22 and 28 bytes**, which is the
    band, and the `json_post` family sits entirely above 29 while `rest_path` and `search_query`
    sit entirely below 22 and are invisible for a different reason.

    **Why it is its own threat and not a line inside threat 12.** Threat 12 is about the numbers
    being a lower bound, which is a statement about what the sensor sees at capture time and is
    safe in the direction it errs. This is about what survives to disk, and it errs in the other
    direction: the run REPORTS a match that a later audit of the stored digests cannot confirm. A
    reviewer handed the persisted fingerprints and asked to re-derive a published attribution can
    fail to, on material where the capture was correct. "Our numbers are floors" does not answer
    that; it is the opposite failure mode.

    **Two ways out, both with a real cost, and the decision is deferred on purpose.**

    - *Persist the exact digests of the matched regions*, alongside the winnowed fingerprints.
      Re-verification then always succeeds, because the auditor checks the same digests the match
      was made from. The cost is that it widens the privacy surface negative 2 exists to bound: a
      winnowed fingerprint is a lossy sample of a document, while a per-match digest set is a
      targeted record of exactly the fragments that travelled, which is a stronger handle on the
      content even though it is still a digest. Salted, so not directly invertible; but a holder of
      the salt and a candidate corpus can confirm specific fragments, and "we keep only digests" is
      a weaker promise once the digests are chosen for their relevance.
    - *Raise the persisted floor to the matching floor*, by winnowing at a window that guarantees
      every k-gram is kept (w = 1), or by matching only at or above w + k - 1. The privacy surface
      does not move. The cost is paid in storage for the first option and in recall for the second:
      a rule of 29 bytes drops the entire 22-to-28 band from the numbers, and every dropped match
      pushes the attributable share down, which is the safe direction but a real loss on the exact
      material (`doc_url`, ordinary document URLs) where realistic arguments do match.

    **Not decided now, and not decided by whoever hits it first.** The choice is a trade between
    negative 2 and external auditability, which is a product decision rather than a measurement
    one, and phase B's results are part of its input: if the 22-to-28 band turns out to carry a
    negligible share of real matches, the second option costs nothing and wins. Revisit after the
    phase B concurrent pass, with the band's measured share in hand.
