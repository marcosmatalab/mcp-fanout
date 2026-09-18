# mcp-fanout Makefile.
# Doctrine rule 6: no published number without a command that measures it.
# Every n<N> target below is that command for number <N>. `make numbers` runs all six.
#
# We set RECIPEPREFIX to '>' so recipe lines do not depend on literal tabs.
.RECIPEPREFIX = >
.PHONY: install verify test selftest run numbers n1 n2 n3 n4 n5 n6 figures clean

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

# Full capture against the pinned servers. Needs Docker + network + the capture extra.
# Writes runs/<timestamp>/flows.jsonl. See docs/METHOD.md and docs/THE-GATE.md.
run:
> python3 -m mcpfanout.cli run --registry registry/servers.yaml --out runs/

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

# Write the latest run's normalized aggregate into docs/figures/ as a committed artifact.
# This is what makes a figure quoted in a document re-derivable without committing the run
# itself (docs/THE-GATE.md, rules 1 and 4). Counts only: no host, no server id, no digest.
figures:
> python3 -m mcpfanout.cli figures --run $(RUN) --out docs/figures

clean:
> rm -rf build dist src/*.egg-info .pytest_cache
> find . -type d -name __pycache__ -prune -exec rm -rf {} +
