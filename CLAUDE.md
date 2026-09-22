# CLAUDE.md

Operating rules for any agent working in this repository. Read this before touching anything.

**This file is a deliberate artifact of the method, not leftover scaffolding.** The code here was
implemented with Claude Code, inside rules fixed BEFORE the first commit rather than derived from
what came out of it. It stays in the repository root, and is declared in the README under "How this
was built", because 48 of the first 50 commits carry a `Co-Authored-By` trailer and a public history
is not something a deleted file hides. What is worth judging is the harness, not the authorship: the
rules below, the gates behind `make gates`, and the sealed pre-registration are what an agent may
not talk its way past.

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

## The rules, and the one place each of them lives

Three files and one source per rule, because a rule written twice is a rule that goes wrong in one
of the two places and stays right in the other, which is how it survives review. This file is the
operating manual: what to run, what is already measured, what not to rediscover. It does not restate
the rules, it names them and points at their source.

- **The four negatives**, which are the product thesis and not style preferences: **never inject**,
  **never store content**, **never infer**, **never act on what is observed**. Violating one
  invalidates the work. Defined, each with its why and what it costs, in `docs/DOCTRINE.md`. Read
  them there before the first edit; the four clauses above are an index, not the rule.
- **The ten gate rules**, the conditions a run must pass before any number from it is reported, are
  defined in `docs/PROTOCOL.md`, part 1. Two of them bind every task here and not only a capture:
  **rule 6**, no published figure without a command that measures it, which applies to the README
  and to this file as much as to a figure; and **rule 10**, every instrument needs a test that goes
  red when the instrument is ABSENT and not only when it is wrong, because a wrong number gets
  investigated and a green gets published. `docs/PROTOCOL.md` lists the ten times this repository
  produced that failure, and what a test has to do to catch it.

## Hard rules for any change

- **Tests stay green.** `make verify` must pass before you consider a task done. Currently 692
  tests. If you add behaviour, add a test. Update this count when you change it: a hard rule
  quoting a stale figure is the same defect rule 6 exists to prevent, one file closer to home.
- **The measurement core stays standard-library only**, and the list of what counts as the core is
  now in `tests/test_core_has_no_dependencies.py` rather than in this sentence, because a list in
  prose is a list that drifts. The capture layer (`driver`, `capture_addon`, `harness/`) may use
  the `capture` extra (mitmproxy, PyYAML). This is why every registry file the core reads is JSON
  and not YAML, and it is deliberate: the core is what CI runs and what must be reproducible, and a
  transitive dependency changing a number is exactly the supply-chain failure this project studies.
  Two checks, because they fail differently: the static one in that test, and the `core-isolation`
  job that installs without the extra.
- **Every design decision carries its why and its trade-off**, in the code itself and in the docs:
  why this path and not another, how it handles data and errors, cost, latency, reproducibility.
  Write at a level that survives a demanding technical examiner. Rigor over polish.
- **Statistical variables only where the problem is genuinely probabilistic.** In this repo that is
  hash collisions and nothing else. Matching is deterministic; do not dress it in statistics.
- **Never commit a CAPTURED run.** `runs/` is gitignored except for two REDACTED runs,
  `runs/example-sequential` and `runs/example-concurrent`, produced by `tools/redact_run.py`, where
  every server id, tool name, destination and address is a stable label and every digest is kept.
  They exist because `make n1` failed in a clean clone. The exception is written down, its cost is
  reported in the output (a redacted run cannot be re-classified against a newer registry), and
  `tests/test_example_runs.py` fails if they stop reproducing the published figures. Everything
  else about a capture stays untracked: it states, per server, where that server went and when.
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
- **Run `make gates` before calling anything done.** It is the whole CI pipeline: the suite, the
  claims gate, the figures gate, the corpus gate, the pre-registration, the reproduction of the
  headline number from the committed runs, lint, types and both coverage floors. Two of those
  REGENERATE rather than inspect, because a check that does not execute the instrument cannot tell
  a stale artifact from a current one.
- **A committed artifact is never hand-edited**, not even to repair a renamed path. It records what
  the code said when the run was taken; `make figures-check` fails on any edit to one.

## Layout

```
src/mcpfanout/   measurement core (stdlib only) + driver and capture addon
harness/         Docker image, run.sh orchestration, drive_all.py, probe.py
corpus/context/  synthetic bait files with unique CANARY_ tokens (never real secrets)
corpus/calls/    the SEQUENTIAL per-server corpus: one call at a time, carries the canary
corpus/concurrent/  the CONCURRENT per-server corpus: realistic arguments that SHARE structure,
                 no canary, driven as waves of N. Read its README before editing one
corpus/negative/ the negative control: call pairs that share language structure and NO
                 information. held-out.json is the published half, four families and 224 pairs;
                 calibration.json is the tuning half and has five, 280 pairs, since the structural
                 matcher was pre-registered. reserved.json is the live reserve for the structural
                 work, generated by tools/build_negative_extras.py, never measured. The loader's
                 refusal is a COURTESY, not a lock, and says so (docs/PREREG-F2.md section 1)
corpus/positive/ the phase A positive control: what the bench actually sent, distilled from its own
                 ledger by `make positive`, so the k sweep needs no Docker
corpus/background/  the documents whose k-gram frequencies define "common" for F1.3. Found material
                 plus the calibration half, never the reserved half. Read its README
bench/           phase A: our own MCP server, our own HTTP sink, the wave plan.
                 server.py and sink.py import NOTHING from mcpfanout, by test
tools/           generators for data that must be re-derivable rather than hand-edited, plus
                 redact_run.py (a capture to a publishable run), the two SVG renderers,
                 word_budget.py (the declared documentation budget) and release_notes.py (the
                 release's notes, derived from the signed tag and verified against what was
                 published)
registry/        servers.yaml (what to measure, with max_concurrency per server),
                 client-constant-paths.json (the number 5 content denominator, FROZEN by sha256
                 in docs/PREREG-F2.md: adding an entry moves a pre-registered denominator),
                 selfhostable.json (number 6 classification), package-infrastructure.json
                 (number 1 exclusion list), declared-destinations.json (gate rule 7),
                 probes/ (real tool schemas)
docs/            DOCTRINE (the four negatives and the privacy boundary), METHOD (the observation
                 model and the six numbers), PROTOCOL (the gate, the phases and the stop criteria,
                 merged from three files), CALIBRATION, THREATS, PREREG-F2, DISCLOSURE-LOG
docs/figures/    committed normalized aggregates: the re-derivable half of a run.
                 figures/control/ is the ONE family allowed to name a server, and only under an
                 authorisation recorded in docs/DISCLOSURE-LOG.md (gate rule 7, not an exception
                 to gate rule 3 but the path rule 7 describes)
docs/disclosure/ the text of what was actually sent to a maintainer, kept so it is recoverable
runs/            untracked, EXCEPT example-sequential and example-concurrent, which are redacted
                 (runs/README.md). They are what makes `make reproduce` work in a clean clone
tests/           the core test suite plus a mock MCP server
```

A draft write-up lives on the `paper` branch and is deliberately not in `main`: it duplicated the
README's argument and read as unfinished work inside the code.

## Running it

```bash
source .venv/bin/activate
make gates       # EVERYTHING CI runs, in the order CI runs it. This is the one to use
make verify      # 692 tests, no Docker, no network
make selftest    # synthetic run, no Docker
make reproduce   # the headline number end to end from the committed example runs
make numbers     # the six numbers from a run (RUN defaults to the committed example-concurrent)
make claims-check    # every figure in the README against the artifact of the pass that may publish it
make figures-check   # regenerate every calibration figure and both SVGs; fails on a non-empty diff
make lint / types / cov   # ruff, mypy --strict, and the 85% / 60% coverage floors
make figures     # commit a run's normalized aggregate to docs/figures/
make run         # phase B SEQUENTIAL pass: real capture, one call in flight. Docker + network
make run-concurrent  # phase B CONCURRENT pass: waves of N = 2, 5, 10. A separate run, separate figure
make disclosure  # gate rule 7: destinations nobody declared. Non-zero exit means stop
make control     # gate rule 7's second half: launch a bare browser through the same proxy with no
                 # MCP server and compare destinations. Non-zero exit IS the result: it means the
                 # control did NOT explain the finding. Docker + network
make control-publish AUTH="..."  # commit the comparison as a figure that NAMES the instance.
                 # Refuses without the authorisation record (docs/DISCLOSURE-LOG.md)
make words       # the documentation budget: findings against rules of operation. Declared in
                 # docs/README.md and gated by tests/test_word_budget.py
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
  material 0.475 to 0.4, and every miss pushes the attributable share down, which is the safe
  direction. The constant in `shingle.py` cites the curve beside it. **Do not re-tune k by hand**:
  it is the output of `calibrate.choose_k`, and the registry, the addon and run.sh all read it now
  instead of keeping copies.
- **F1.3, done and REVERTED. Do not switch it back on without new evidence.** `make rarity`, which
  exits non-zero because the rate did not fall: 0 of 224 unweighted against 0 of 224 weighted on the
  reserved half at k = 22. Probed at k = 16, where false positives still exist, it removed 4 of 62 on
  the calibration half and 0 of 66 on the reserved one. The diagnosis is measured, not guessed: every
  colliding k-gram appears in at most ONE of the 32 background documents, so nothing can be weighted
  down, and a mass threshold high enough to clear the false positives (6.0) is thresholding match
  LENGTH and costs recall the k choice does not (0.3 against 0.4). The code stays in
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
   0.80 were measured with a proxy blind to Node's global `fetch` (threat 19), so they described a
   flow sample biased toward the servers using proxy-honouring clients. They are superseded, not
   retracted.

   The cause is measured and is a finding, not a tuning problem: **containment's power depends on
   the shape of a tool's arguments.** A tool taking a URL or a path decomposes into four or five
   structural tokens and attributes uniquely; a tool taking one free-text query is ONE token and
   can only be CONTENT_AMBIGUOUS, because one token identifies a class and not a call. Six of the
   thirteen missing attributions are exactly that, all on the newly visible server.

   What the write-up must carry is listed in `docs/PREREG-F2.md` section 13, including the
   pre-registered claim that turned out false and is still inside the seal.

1. **19 October 2026, and it is twenty minutes.** The disclosure window closes. Record the
   maintainers' responses in `docs/DISCLOSURE-LOG.md`, or `no response as of the publication
   date`, which the log already says is the honest outcome and which is why it was written before
   the result was known. Then tag `v1.0.0`, publish the release, and add the two Zenodo DOIs where
   `CONTRIBUTING.md` says each one goes. It is the only item here that cannot be done early.

2. **Phase C, attacking attribution adversarially**: the same fragment across concurrent calls on a
   real server, pooled connections, delayed egress. Phase A shows the sensor can discriminate when
   the pattern is ours to design; phase C is where it is not. Not started, and the README says so
   rather than implying the concurrent pass covered it.

3. **Threat 16, still undecided and now measurable.** A match between 22 and 28 bytes enters the
   numbers and may not be re-derivable from the persisted digests, which is the property an
   external auditor presses first. Two options with their costs are in `docs/THREATS.md` threat 16;
   the input the decision waits on is the band's measured share of real matches.

4. **Standing, none blocking.** The `redact.py` PENDING gaps, which `docs/DOCTRINE.md` promotes
   from to-dos to PRECONDITIONS of any deployment: a per-installation key with rotation, and a
   minimum-fragment-length policy. And the bench's HTTP-only limit, if a TLS-specific capture
   defect ever needs ruling out.

**What is done, so it is not redone.** Phase A passes its pre-registered sensor gate (capture
recall 1.0, zero false strong attributions over 33 strong claims, false provenance 0.0). Both phase
B passes are driven, published and clear of gate rule 7, and both are committed in redacted form
under `runs/` so every number reproduces offline. The calibration block F1 is complete, k is chosen
by the curve, and rarity weighting is measured and reverted. Lab accounts are decided (github
only). The corpus is aligned against the real schemas and the protocol defect is fixed.

**Do not credential another server whose client ignores the proxy** until transparent interception
or eBPF exists: the github token worked and changed no published number, because that server's
client does not honour `HTTP_PROXY` (threat 6, re-measured with 10 direct SYNs). The credential
buys a connection nobody can read.

## Commit style

Imperative subject, body explaining why and the trade-off, not just what. End with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
