# mcp-fanout Makefile.
# Doctrine rule 6: no published number without a command that measures it.
# Every n<N> target below is that command for number <N>. `make numbers` runs all six.
#
# We set RECIPEPREFIX to '>' so recipe lines do not depend on literal tabs.
.RECIPEPREFIX = >
.PHONY: install verify test selftest run run-concurrent numbers n1 n2 n3 n4 n5 n6 figures bench \
        bench-verify disclosure control control-publish fp fp-calibration ksweep positive rarity \
        inventory f2 f2-reserved corpus-check backstop clean

RUN ?= latest

install:
> python3 -m pip install -e ".[dev]"

# Prove the measurement core is deterministic byte for byte over fixtures.
# This runs WITHOUT Docker or network: it is the part CI can trust.
verify:
> python3 -m pytest tests/ -q

test: verify

# Build a synthetic run and show its numbers, with no Docker and no network. Demonstrates the
# full compute path deterministically. The run is clearly labeled selftest, never a measurement.
selftest:
> python3 -m mcpfanout.cli selftest --out runs/selftest

# Phase B, SEQUENTIAL pass: one call in flight per server, from corpus/calls/. This is the pass
# numbers 1, 2, 3 and 4 are read from. Needs Docker + network + the capture extra.
# Writes runs/<timestamp>-sequential/flows.jsonl. See docs/PHASES.md and docs/THE-GATE.md.
run:
> python3 -m mcpfanout.cli run --registry registry/servers.yaml --out runs/ --pass sequential

# Phase B, CONCURRENT pass: waves of N calls in flight per server, from corpus/concurrent/, with N
# on the bench's own ladder (2, 5, 10) capped per server. This is the ONLY pass number 5 may be
# read from: with one call in flight the strongest grade is unreachable by construction.
# A separate run and a separate figure, never merged with the sequential one (docs/PHASES.md).
run-concurrent:
> python3 -m mcpfanout.cli run --registry registry/servers.yaml --out runs/ --pass concurrent

# F2: the structural matcher's predictions (docs/PREREG-F2.md), on CALIBRATION material.
# This is the one to look at while working. It re-derives sections 4 and 5 of the
# pre-registration, which is the rule 6 debt that document declared.
f2:
> python3 tools/measure_f2.py

# F2 on the RESERVED half. Measured ONCE, at the end, and its figure is what gets published.
# A separate target from `f2` on purpose: a single command that could be pointed at either half
# is a command somebody points at the wrong one, which is how the previous reserve was lost.
f2-reserved:
> python3 tools/measure_f2.py --reserved

# The negative corpus's generated halves, re-derived. Fails if either was edited by hand.
corpus-check:
> python3 tools/build_negative_extras.py --check

# Outbound TCP SYNs per destination from a run's pcap backstop. The evidence behind threat 6:
# a client that ignores HTTP(S)_PROXY is invisible to the proxy and visible only here.
backstop:
> python3 tools/pcap_syns.py --run $(RUN)

# All six numbers from a run (default: the latest run under runs/).
numbers:
> python3 -m mcpfanout.cli aggregate --run $(RUN) --number all

n1:
> python3 -m mcpfanout.cli aggregate --run $(RUN) --number 1
n2:
> python3 -m mcpfanout.cli aggregate --run $(RUN) --number 2
n3:
> python3 -m mcpfanout.cli aggregate --run $(RUN) --number 3
n4:
> python3 -m mcpfanout.cli aggregate --run $(RUN) --number 4
n5:
> python3 -m mcpfanout.cli aggregate --run $(RUN) --number 5
n6:
> python3 -m mcpfanout.cli aggregate --run $(RUN) --number 6

# Phase A bench: build the instrument's own measurement. Needs Docker and network.
# Gate rule 8: this must pass before any phase B figure is published.
bench:
> python3 -m mcpfanout.cli run --bench --out runs/

# The instrument block from a bench run: capture recall, attribution precision, false provenance.
bench-verify:
> python3 -m mcpfanout.cli bench-verify --run $(RUN)

# F1.1, the published figure: how often the matcher claims a coincidence that does not exist, over
# concurrent call pairs that share language structure and no information. Measured on the HELD-OUT
# half, which is touched once, at the end, and never used to tune anything. Needs no Docker.
fp:
> python3 -m mcpfanout.cli calibrate --half held_out --out docs/figures/calibration

# The same measurement on the CALIBRATION half. This is the one to look at while working: choosing
# k or a threshold against the held-out half would publish the corpus's own opinion of the matcher,
# and the loader refuses it (docs/CALIBRATION.md).
fp-calibration:
> python3 -m mcpfanout.cli calibrate --half calibration --out docs/figures/calibration

# F1.2, the k sweep: false positives and recall against k over 8..64, and the k the written rule
# picks. Calibration half only, and sweep_k refuses any other. Needs no Docker: the positive control
# is the bench's own transfers, distilled once into corpus/positive/ by `make positive`.
ksweep:
> python3 -m mcpfanout.cli ksweep --out docs/figures/calibration

# Re-distil the phase A positive control from a bench run. Run this after `make bench` if the bench
# changes what it sends; the k sweep reads the committed fixture, not the run.
positive:
> python3 -m mcpfanout.cli prep-positive --run $(RUN)

# The self-match ceiling and its decomposition: how much of realistic argument material the sensor
# can see at all, by length bucket, against both thresholds (exact k-gram match, and the winnowing
# guarantee w + k - 1). This is the figure that makes number 5 a lower bound. Needs no Docker.
inventory:
> python3 -m mcpfanout.cli inventory --out docs/figures/calibration

# F1.3: does weighting a k-gram by how common it is lower the false-positive rate? Exit 0 if it
# does (keep it), 1 if it does not (revert it, document why). Needs no Docker.
#
# A NON-ZERO EXIT HERE IS THE RESULT, not a broken build. It currently exits 1, and the verdict and
# the numbers behind it are in docs/CALIBRATION.md, F1.3. Do not wrap this in `|| true` to make it
# quiet: the exit code is the only part of the measurement that cannot be misread.
rarity:
> python3 -m mcpfanout.cli rarity --out docs/figures/calibration

# Gate rule 7: which of a run's destinations nobody declared. Exits non-zero if any server needs
# reviewing, or if the declaration file is missing (unevaluated is not the same as satisfied).
# Operator-only output: it names servers and hosts, so it stays in the run directory.
disclosure:
> python3 -m mcpfanout.cli disclosure-check --run $(RUN)

# The browser control for gate rule 7: launch a bare headless browser through the same proxy, with
# NO MCP server in the process tree, and compare where it goes against where the server went. This
# is what turns "that destination is the embedded browser's" from a plausible reading of a hostname
# into a measured attribution of cause. Needs Docker + network.
#
# A NON-ZERO EXIT IS A RESULT: it means the bare browser did NOT reach a host the server was
# flagged for, so the browser does not explain the finding. Do not wrap it in `|| true`.
CONTROL_SERVER ?= puppeteer
AGAINST ?= latest-sequential
CONTROL_RUN ?= latest-control
control:
> python3 -m mcpfanout.cli run --control --against $(AGAINST) --out runs/

# Commit the comparison as a figure that NAMES the instance. Separate from `make control` on
# purpose: gate rule 7 allows naming a server only after the finding has been disclosed, so the
# authorisation record is a required argument and the command refuses without it.
#   make control-publish AUTH="Marcos Mata, 2026-09-19, docs/DISCLOSURE-LOG.md#2026-09-19-puppeteer"
control-publish:
> @test -n "$(AUTH)" || { echo "AUTH= is required: gate rule 7 (see docs/DISCLOSURE-LOG.md)"; exit 2; }
> python3 -m mcpfanout.cli control-compare --run $(CONTROL_RUN) --against $(AGAINST) \
>   --server $(CONTROL_SERVER) --publish docs/figures/control --authorisation "$(AUTH)"

# Write the latest run's normalized aggregate into docs/figures/ as a committed artifact.
# This is what makes a figure quoted in a document re-derivable without committing the run
# itself (docs/THE-GATE.md, rules 1 and 4). Counts only: no host, no server id, no digest.
figures:
> python3 -m mcpfanout.cli figures --run $(RUN) --out docs/figures

clean:
> rm -rf build dist src/*.egg-info .pytest_cache
> find . -type d -name __pycache__ -prune -exec rm -rf {} +
