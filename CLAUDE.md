# CLAUDE.md

Operating rules for any agent working in this repository. Read this before touching anything.

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

## Rule 6: no number without a command

Every published figure has a `make` target and an `aggregate` subcommand behind it. If you add a
claim, add the command that measures it, or do not add the claim. This applies to the README too.

## Hard rules for any change

- **Tests stay green.** `make verify` must pass before you consider a task done. Currently 128
  tests. If you add behaviour, add a test. Update this count when you change it: a hard rule
  quoting a stale figure is the same defect rule 6 exists to prevent, one file closer to home.
- **The measurement core stays standard-library only.** `shingle`, `redact`, `match`, `classify`,
  `record`, `aggregate`, `demo`, `cli` must not gain third-party dependencies. The capture layer
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

Before any number from a run is reported, `docs/THE-GATE.md` must hold: reproducible, a command
behind every number, no names in aggregate output, no content stored, container only and no real
credentials, threats to validity written, responsible disclosure if a server egresses somewhere
its documentation does not declare.

## Layout

```
src/mcpfanout/   measurement core (stdlib only) + driver and capture addon
harness/         Docker image, run.sh orchestration, drive_all.py, probe.py
corpus/context/  synthetic bait files with unique CANARY_ tokens (never real secrets)
corpus/calls/    the fixed per-server tool-call corpus
registry/        servers.yaml (what to measure), selfhostable.json (number 6 classification),
                 package-infrastructure.json (number 1 exclusion list), probes/ (real tool schemas)
docs/            doctrine, method, the six numbers, the gate, threats, stop criteria
tests/           the core test suite plus a mock MCP server
```

## Running it

```bash
source .venv/bin/activate
make verify      # 128 tests, no Docker, no network
make selftest    # synthetic run, no Docker
make numbers     # the six numbers from the latest run
make run         # real capture, needs Docker and network
```

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

## Pending work, in order

Items 1 to 3 of the previous list are done: the corpus is aligned against the real schemas and
gated by `tests/test_corpus_matches_probes.py`, `registry/servers.yaml` is pinned to exact
versions with measured per-server facts, and the protocol defect is fixed. A one-server capture
of `fetch` has run end to end.

1. **Build the phase A bench** (`docs/PHASES.md`): two or three of our own MCP servers with known
   egress to our own destinations. Until it passes the sensor gate, no phase B figure may be
   published. That is gate rule 8, and it blocks everything below it.
2. **Then** the ten-server phase B capture.
3. **Then** phase C, attacking attribution with concurrent calls. Only there can
   `CONTENT_UNIQUE` be earned; see `docs/DOCTRINE.md`, the evidence model.

## Commit style

Imperative subject, body explaining why and the trade-off, not just what. End with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
