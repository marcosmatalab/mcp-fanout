# CLAUDE.md

Operating rules for any agent working in this repository. Read this before touching anything.

**This file is a deliberate artifact of the method, not leftover scaffolding.** This repository was
written with the assistance of a coding agent, and the rules below were fixed BEFORE the agent
started rather than derived from what it produced: four hard negatives, ten gate rules, and rule 6,
no published figure without a command that measures it. It is kept in the repository root, and
declared in the README under "How this was built", because 48 of the first 50 commits carry a
`Co-Authored-By` trailer and a public history is not something a deleted file hides. The doctrine
in `docs/DOCTRINE.md` is the same argument written for a reader rather than for the agent.

## What this repo is

`mcp-fanout` is a **measurement harness**, not a product. It exists to produce six numbers that
decide whether a runtime tool-call tracing product is viable and which of two architectures it
should have. Read `README.md`, then `docs/METHOD.md`. Do not turn it into a gateway, a firewall,
a DLP product, or a monitoring service.

The product it would serve, if the numbers justify one, is **runtime provenance and evidence for
autonomous agents**, with MCP as the first supported environment and not the category. Not "MCP
security": that binds the product to a protocol still changing under it and to a function a
gateway absorbs. Not "data lineage": that is Cyberhaven's category, with the brand and the
capital already in it. Keep the code written in terms of an agent's action and its egress, so a
second environment is an adapter rather than a rewrite.

## Language

- Repo content (code, comments, docs, commit messages): **English**.
- Talking to Marcos: **direct, informal Castilian Spanish**, unfiltered and honest. No diplomatic
  hedging. If something he proposes is wrong, say it is wrong and why.
- In documents written for him: **no em dashes**. Use commas or colons.

## The four negatives (never)

These are not style preferences. They are the product thesis. Violating one invalidates the work.

1. **Never inject.** Nothing is planted inside a third party: no marker, no token, no code, no
   identifier smuggled into a call toward someone else's system. The observer lives at the own
   edge.
2. **Never store content.** Only salted digests and references. Raw payloads exist in memory
   during the hashing pass and nowhere else. Enforced in `src/mcpfanout/redact.py`.
3. **Never infer.** Byte-literal matching only. No paraphrase detection, no semantic propagation,
   no model in the loop guessing what a server forwarded. A miss is a false negative and that is
   the safe direction.
4. **Never act on what is observed.** Observe and record. Do not block, redact in flight, alter,
   or intervene.

Full text in `docs/DOCTRINE.md`.

## Rule 10: an absent instrument must fail, not pass quietly

Every instrument needs a test that goes red when the instrument is ABSENT, not only when it is
wrong. A wrong number gets investigated; a green gets published. This repo has produced that
failure seven times, listed in `docs/PROTOCOL.md`: an addon that did not load and finished green
with zero flows, a k constant that diverged and silently stopped matching, a selftest that
serialised the structural fields without ever populating one, and, past code, a README and four
calibration figures that went on stating what the measurements no longer said. Asserting a field is
PRESENT is not enough, every one of them had its fields. Asserting the SHAPE of an artifact is not
enough either. Assert the value only a working instrument could compute, through its real entry
point, and for a committed artifact that means regenerating it and comparing.
The rule applies to itself: a detector must catch a planted instance in the same run before its
clean report counts. Full text in `docs/PROTOCOL.md` rule 10.

## Rule 6: no number without a command

Every published figure has a `make` target and an `aggregate` subcommand behind it. If you add a
claim, add the command that measures it, or do not add the claim. This applies to the README too.

## Hard rules for any change

- **Tests stay green.** `make verify` must pass before you consider a task done. Currently 603
  tests. If you add behaviour, add a test. Update this count when you change it: a hard rule
  quoting a stale figure is the same defect rule 6 exists to prevent, one file closer to home.
- **The measurement core stays standard-library only.** `shingle`, `redact`, `match`, `classify`,
  `record`, `aggregate`, `disclosure`, `control`, `calibrate`, `rarity`, `demo`, `cli` must not gain
  third-party dependencies. This is
  why every registry file the core reads is JSON and not YAML. The capture layer
  (`driver`, `capture_addon`, `harness/`) may use the `capture` extra (mitmproxy, PyYAML). This is
  deliberate: the core is what CI runs and what must be reproducible, and a transitive dependency
  changing a number is exactly the supply-chain failure this project studies.
- **Every design decision carries its why and its trade-off**, in the code itself and in the docs:
  why this path and not another, how it handles data and errors, cost, latency, reproducibility.
  Write at a level that survives a demanding technical examiner. Rigor over polish.
- **Statistical variables only where the problem is genuinely probabilistic.** In this repo that is
  hash collisions and nothing else. Matching is deterministic; do not dress it in statistics.
- **Never commit a run.** `runs/` is gitignored. A run may carry salted digests tied to a specific
  server, and gate rule 3 forbids naming servers in anything published.
- **Aggregate output names nothing.** No server id, host, or tool name. There is a test enforcing
  this (`tests/test_aggregate.py::test_aggregate_output_leaks_no_server_names`). Keep it passing.
- **Never discard unstaged work.** `git checkout -- <path>` and `git restore <path>` are
  forbidden on work that is not staged. To throw something away, use `git stash push -m "<why>"`,
  which is recoverable. This cost real edits three times in one session, always the same way: a
  file is mutated on purpose to prove a test bites, `checkout` undoes the mutation, and every
  other unstaged change under that path goes back to HEAD with it. To mutate a file for a test,
  copy it outside the repo first (`cp <file> "$SCRATCH/<file>.bak"`, mutate, run, copy back), or
  `git add` before mutating so `checkout` restores the right thing.
- **Weigh cost against benefit explicitly** when proposing work, in euros and hours. The budget is
  tight. Say what something costs before building it.

## The gate

Before any number from a run is reported, `docs/PROTOCOL.md` must hold: reproducible, a command
behind every number, no names in aggregate output, no content stored, container only and no real
credentials, threats to validity written, responsible disclosure if a server egresses somewhere
its documentation does not declare, the instrument passing before the phenomenon is measured, and
the matcher calibrated on real language before any volume is measured (rule 9,
`docs/CALIBRATION.md`).

## Layout

```
src/mcpfanout/   measurement core (stdlib only) + driver and capture addon
harness/         Docker image, run.sh orchestration, drive_all.py, probe.py
corpus/context/  synthetic bait files with unique CANARY_ tokens (never real secrets)
corpus/calls/    the SEQUENTIAL per-server corpus: one call at a time, carries the canary
corpus/concurrent/  the CONCURRENT per-server corpus: realistic arguments that SHARE structure,
                 no canary, driven as waves of N. Read its README before editing one
corpus/negative/ the negative control: call pairs that share language structure and NO
                 information. calibration.json and held-out.json are BOTH calibration material now
                 (held-out.json was measured through a bare json.load on 2026-09-19 and lost its
                 reserve status). reserved.json is the live reserve, generated by
                 tools/build_negative_extras.py, never measured. The loader's refusal is a
                 COURTESY, not a lock, and says so (docs/PREREG-F2.md section 1)
corpus/positive/ the phase A positive control: what the bench actually sent, distilled from its own
                 ledger by `make positive`, so the k sweep needs no Docker
corpus/background/  the documents whose k-gram frequencies define "common" for F1.3. Found material
                 plus the calibration half, never the reserved half. Read its README
bench/           phase A: our own MCP server, our own HTTP sink, the wave plan.
                 server.py and sink.py import NOTHING from mcpfanout, by test
tools/           generators for data that must be re-derivable rather than hand-edited
registry/        servers.yaml (what to measure, with max_concurrency per server),
                 client-constant-paths.json (the number 5 content denominator, FROZEN by sha256
                 in docs/PREREG-F2.md: adding an entry moves a pre-registered denominator),
                 selfhostable.json (number 6 classification), package-infrastructure.json
                 (number 1 exclusion list), declared-destinations.json (gate rule 7),
                 probes/ (real tool schemas)
docs/            doctrine, method, the six numbers, the gate, phases, threats, stop criteria
docs/figures/    committed normalized aggregates: the re-derivable half of a run.
                 figures/control/ is the ONE family allowed to name a server, and only under an
                 authorisation recorded in docs/DISCLOSURE-LOG.md (gate rule 7, not an exception
                 to gate rule 3 but the path rule 7 describes)
docs/disclosure/ the text of what was actually sent to a maintainer, kept so it is recoverable
tests/           the core test suite plus a mock MCP server
```

## Running it

```bash
source .venv/bin/activate
make verify      # 603 tests, no Docker, no network
make selftest    # synthetic run, no Docker
make numbers     # the six numbers from the latest run
make figures     # commit the latest run's normalized aggregate to docs/figures/
make run         # phase B SEQUENTIAL pass: real capture, one call in flight. Docker + network
make run-concurrent  # phase B CONCURRENT pass: waves of N = 2, 5, 10. A separate run, separate figure
make disclosure  # gate rule 7: destinations nobody declared. Non-zero exit means stop
make control     # gate rule 7's second half: launch a bare browser through the same proxy with no
                 # MCP server and compare destinations. Non-zero exit IS the result: it means the
                 # control did NOT explain the finding. Docker + network
make control-publish AUTH="..."  # commit the comparison as a figure that NAMES the instance.
                 # Refuses without the authorisation record (docs/DISCLOSURE-LOG.md)
make fp          # gate rule 9: the matcher's false-positive rate on the RESERVED half (published)
make fp-calibration  # the same rate on the calibration half: this is the one to look at while working
make ksweep      # F1.2: the false-positive and recall curves against k, and the k the rule picks
make rarity      # F1.3: the rarity-weighting verdict. Non-zero exit IS the result, not a failure
make bench       # phase A bench capture
make bench-verify    # the instrument block from a bench run
```

**Phase B is two passes and they are never one run.** `corpus/calls/` sequentially for numbers 1 to
4; `corpus/concurrent/` in waves for number 5. Driven sequentially, strong attribution is 0.0 by
construction, so a single sequential phase B run does not measure the thesis, it makes it
unobservable. Driven concurrently, a per-call fan-out figure is a figure about our own wave size.
`docs/PROTOCOL.md` carries the full argument and the pre-registered predictions, which are frozen by
digest in `tests/test_phase_b_prediction.py`: editing them after a result fails the suite.

## Measured facts already established (do not rediscover)

Verified on 2026-09-18 against the live registries:

- Package versions that resolve: `@modelcontextprotocol/server-everything@2026.8.31`,
  `server-filesystem@2026.8.31`, `server-memory@2026.8.31`,
  `server-sequential-thinking@2026.8.31`, `server-brave-search@0.6.2`,
  `server-github@2025.4.8`, `server-puppeteer@2025.5.12`, `server-slack@2025.4.25`,
  `server-postgres@0.6.2`, `server-google-maps@0.6.2`, `server-gdrive@2025.1.14`;
  PyPI: `mcp-server-fetch==2026.8.18`, `mcp-server-git==2026.8.18`,
  `mcp-server-time==2026.8.18`, `mcp-server-sqlite==2025.4.25`.
  Note `@modelcontextprotocol/server-sequentialthinking` (no hyphen), `server-fetch`,
  `server-sqlite` and `server-time` do NOT exist on npm.
- Real tool counts, all ten probed 2026-09-18 and committed under `registry/probes/`: github 26,
  filesystem 14, everything 13, git 12, memory 9, puppeteer 7, time 2, brave-search 2, fetch 1,
  sequential-thinking 1. Nine started with no credentials; brave-search exits before the
  handshake without `BRAVE_API_KEY`.
- **Former defect, now fixed (do not re-fix).** `driver.PROTOCOL_VERSION` was `"2026-07-28"`.
  That revision is current AND is where SEP-414 went Final, so the constant was not naming a
  wrong spec: it removed the `initialize` handshake (SEP-2575), which this driver is built on, so
  the harness announced a protocol it does not speak. It is now `"2025-11-25"`, the wire it
  actually implements. See `docs/METHOD.md`, "The protocol revision we speak".

## F1: the calibration block, which gates phase B

Phase A measured false attribution over keyed digests, the most favourable input the matcher will
ever see. Real arguments are natural language and URLs that share structure, and there was no
measurement over those at all. Three pieces, in `docs/CALIBRATION.md`:

- **F1.1, done.** The negative control and the rate: 66 false positives in 224 held-out pairs,
  0.2946, Wilson 95% [0.2388, 0.3574], at k = 16 with no weighting. The spread across families is
  the result, not the pooled figure: one family fails every pair (the server echoes the argument
  envelope), two fail none.
- **F1.2, done. k is 22, not 16, and it was chosen by the curve.** `make ksweep`. False positives
  fall to 0.0 from k = 22 while the phase A bench recall stays at 1.0, and the reserved half agrees:
  0 of 224 pairs, Wilson 95% [0.0, 0.0169]. The cost is priced: self-match recall on realistic
  material 0.5312 to 0.5, and every miss pushes the attributable share down, which is the safe
  direction. The constant in `shingle.py` cites the curve beside it. **Do not re-tune k by hand**:
  it is the output of `calibrate.choose_k`, and the registry, the addon and run.sh all read it now
  instead of keeping copies.
- **F1.3, done and REVERTED. Do not switch it back on without new evidence.** `make rarity`, which
  exits non-zero because the rate did not fall: 0 of 224 unweighted against 0 of 224 weighted on the
  reserved half at k = 22. Probed at k = 16, where false positives still exist, it removed 4 of 62 on
  the calibration half and 0 of 66 on the reserved one. The diagnosis is measured, not guessed: every
  colliding k-gram appears in at most ONE of the 32 background documents, so nothing can be weighted
  down, and a mass threshold high enough to clear the false positives (6.0) is thresholding match
  LENGTH and costs recall the k choice does not (0.375 against 0.5). The code stays in
  `rarity.py`, out of the matching path; a test fails if `match.py` or the addon ever import it while
  the committed verdict reads `reverted`.

**Never tune against the reserved half.** `calibrate.load_negative` raises on it, the CLI derives
the purpose from the half, and tests fail if either guard is bypassed.

## F2: structural containment for number 5, pre-registered and NOT yet built

`docs/PREREG-F2.md`, frozen by `tests/test_prereg_f2_prediction.py`. Number 4 keeps the exact
k-gram matcher; number 5 moves to structural containment. Read the pre-registration before writing
`structure.py`: the predictions, the instrument threshold (0.80 over the frozen content
denominator) and the refusal to freeze a product verdict are all inside the digest.

Two results from it that are NOT matcher work and outrank it:

- **Threat 17**, a tool call runs `npm install` from inside `tools/call`, unpinned and without a
  lockfile. Headline candidate above number 3. Disclosure draft written, NOT yet sent; gate rule 7
  says it goes before publication.
- The privacy boundary in `docs/DOCTRINE.md`: for short tokens a keyed digest is obfuscation, not
  control, and both `redact.py` PENDING gaps are now preconditions of deployment, not to-dos.

## Pending work, in order

0. **DEVELOPMENT IS STOPPED. The next thing is the write-up.** Do not open the per-flow candidate
   variant (declared as amendment A1 and predicted to fail), the response channel, or the
   recursion. Anything added from here competes with writing.

   **The instrument does NOT meet its pre-registered threshold. 0.6579 against 0.80**, run
   `20260919T194649Z-concurrent`, `docs/PREREG-F2.md` section 16. The two earlier figures above
   0.80 were measured with a proxy blind to Node's global `fetch` (threat 19), so they described
   a flow sample biased toward the two servers using proxy-honouring clients. They are superseded,
   not retracted.

   The cause is measured and is a finding, not a tuning problem: **containment's power depends on
   the shape of a tool's arguments.** A tool taking a URL or a path decomposes into four or five
   structural tokens and attributes uniquely; a tool taking one free-text query is ONE token and
   can only be CONTENT_AMBIGUOUS, because one token identifies a class and not a call. Six of the
   thirteen missing attributions are exactly that, all on the newly visible server.

   What the write-up must carry is listed in `docs/PREREG-F2.md` section 13, including the
   pre-registered claim that turned out false and is still inside the seal.

1. **Lab accounts: decided, github only, and the result was instructive.** `docs/METHOD.md`.
   Brave was rejected for the same reason as Google Maps: its free tier requires a credit card
   (checked 2026-09-19). The github token worked and changed no published number, because that
   server's client ignores the proxy (threat 6, re-measured with 10 direct SYNs). Do not
   credential another server whose client ignores the proxy until transparent interception or
   eBPF exists.

2. **Superseded, kept for the record: the next capture was blocked on a decision, not on code.** `docs/METHOD.md` is the plan:
   which accounts the credentialed servers need, the minimum permission each one is, what the
   terms of use questions are (asked, not answered, by the same rule that governs
   `declared-destinations.json`), and what each costs in euros and hours. Recommendation there is
   github plus brave only, 0 euros and under half an hour, because slack and google-maps are not
   in `registry/servers.yaml` at all and each needs half a day of repo work before an account
   helps. Nothing has been created. Until it is decided, a new capture re-measures gagged servers
   and threats 5 and 8 eat the numbers again.

Items 1 to 3 of the previous list are done: the corpus is aligned against the real schemas and
gated by `tests/test_corpus_matches_probes.py`, `registry/servers.yaml` is pinned to exact
versions with measured per-server facts, and the protocol defect is fixed. A one-server capture
of `fetch` has run end to end.

Phase A is built and it passes its pre-registered sensor gate: capture recall 1.0, zero false
strong attributions over 33 strong claims, false provenance 0.0, normalized result reproducible
across two runs. Content matching discriminates between concurrent calls at N up to 10. Measured
figures and the cells in `docs/PROTOCOL.md`; committed artifact under `docs/figures/`.

**The sequential phase B pass is done, published and clear of gate rule 7.** Run
`20260919T115452Z-sequential`, artifact `docs/figures/20260919T115452Z-sequential.json`, cells in
`docs/PROTOCOL.md`, "Observed, sequential pass". Its two undeclared destinations were attributed to
the browser one server embeds, by a control run rather than by reading a hostname (`make control`,
threat 15), carried nothing on either channel, and were disclosed (`docs/DISCLOSURE-LOG.md`).

1. **The concurrent phase B pass.** `make run-concurrent`. It is the only pass number 5 may be read
   from, and the pre-registered predictions B1 and B2 in `docs/PROTOCOL.md` are frozen by digest:
   fill the "Observed, concurrent pass" section from the committed artifact and do NOT edit the
   prediction block when you do.
2. **Then** phase C, attacking attribution adversarially: the same fragment across concurrent
   calls on a real server, pooled connections, delayed egress. Phase A shows the sensor can
   discriminate when the pattern is ours to design; phase C is where it is not.
3. **Decide threat 16 after the concurrent pass**, not before and not by whoever hits it first: a
   match between 22 and 28 bytes enters the numbers and may not be re-derivable from the persisted
   digests, which is the property an external auditor presses first. Two options with their costs
   are written in `docs/THREATS.md` threat 16; the input the decision is waiting on is the band's
   measured share of real matches.
4. Standing items, none blocking: the `redact.py` PENDING gaps (a per-installation key with
   rotation, and a minimum-fragment-length policy) before any real deployment, and the bench's
   HTTP-only limit if a TLS-specific capture defect ever needs ruling out.

## Commit style

Imperative subject, body explaining why and the trade-off, not just what. End with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
