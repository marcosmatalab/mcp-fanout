# mcp-fanout Makefile.
# Doctrine rule 6: no published number without a command that measures it.
# Every n<N> target below is that command for number <N>. `make numbers` runs all six.
#
# We set RECIPEPREFIX to '>' so recipe lines do not depend on literal tabs.
.RECIPEPREFIX = >
.PHONY: install verify test selftest run run-concurrent numbers n1 n2 n3 n4 n5 n6 figures bench \
        bench-verify disclosure clean

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

# Gate rule 7: which of a run's destinations nobody declared. Exits non-zero if any server needs
# reviewing, or if the declaration file is missing (unevaluated is not the same as satisfied).
# Operator-only output: it names servers and hosts, so it stays in the run directory.
disclosure:
> python3 -m mcpfanout.cli disclosure-check --run $(RUN)

# Write the latest run's normalized aggregate into docs/figures/ as a committed artifact.
# This is what makes a figure quoted in a document re-derivable without committing the run
# itself (docs/THE-GATE.md, rules 1 and 4). Counts only: no host, no server id, no digest.
figures:
> python3 -m mcpfanout.cli figures --run $(RUN) --out docs/figures

clean:
> rm -rf build dist src/*.egg-info .pytest_cache
> find . -type d -name __pycache__ -prune -exec rm -rf {} +
