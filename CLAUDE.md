# CLAUDE.md

Operating rules for any agent working in this repository. Read this before touching anything.

## What this repo is

`mcp-fanout` is a **measurement harness**, not a product. It exists to produce six numbers that
decide whether a runtime tool-call tracing product is viable and which of two architectures it
should have. Read `README.md`, then `docs/METHOD.md`. Do not turn it into a gateway, a firewall,
a DLP product, or a monitoring service.

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

- **Tests stay green.** `make verify` must pass before you consider a task done. Currently 23
  tests. If you add behaviour, add a test.
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
registry/        servers.yaml (what to measure) and selfhostable.json (number 6 classification)
docs/            doctrine, method, the six numbers, the gate, threats, stop criteria
tests/           the core test suite plus a mock MCP server
```

## Running it

```bash
source .venv/bin/activate
make verify      # 23 tests, no Docker, no network
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
- Real tool counts from `tools/list`: everything (many), filesystem 14, memory 9,
  sequential-thinking 1.
- **Known defect:** `driver.PROTOCOL_VERSION` is set to `"2026-07-28"`, which the reference server
  accepts but answers with `"2025-11-25"`. Verify the correct current spec revision and fix the
  constant, and check whether the SEP-414 claim in `docs/METHOD.md` cites the right revision.

## Pending work, in order

1. **Align the corpus.** `corpus/calls/*.json` currently names plausible but unverified tools.
   Probe every server with `harness/probe.py`, then rewrite each corpus against the real tool
   names and input schemas. A call to a non-existent tool records zero egress and silently biases
   numbers 1, 2 and 5 downward.
2. **Pin `registry/servers.yaml`** to the exact versions above.
3. **Fix the protocol version defect** noted under measured facts.
4. Only then run a real capture and report numbers.

## Commit style

Imperative subject, body explaining why and the trade-off, not just what. End with:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
