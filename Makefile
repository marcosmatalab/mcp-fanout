# mcp-fanout Makefile.
# Doctrine rule 6: no published number without a command that measures it.
# Every n<N> target below is that command for number <N>. `make numbers` runs all six.
#
# We set RECIPEPREFIX to '>' so recipe lines do not depend on literal tabs.
.RECIPEPREFIX = >
.PHONY: help install verify test selftest run run-concurrent numbers n1 n2 n3 n4 n5 n6 figures bench \
        bench-verify disclosure control control-publish fp fp-calibration ksweep positive rarity \
        inventory f2 f2-reserved corpus-check backstop honesty-curve argument-shapes words clean \
        figures-check curve-svg chain-svg lint types cov claims-check reproduce gates

# The default run is the committed, redacted example (runs/README.md), not "whatever ran last".
# `latest` is right on the machine that captures and wrong everywhere else: in a clean clone it
# fails, and on a developer's machine it silently answers about a different run than the one the
# README quotes. Pass RUN=latest explicitly after a capture.
RUN ?= example-concurrent

.DEFAULT_GOAL := help

# The list a reader needs, in the order they need it. Forty targets is too many to scan, and the
# ones that matter are the four that produce a published figure plus the one that runs every gate.
help:
> @echo "Start here:"
> @echo "  make install      editable install with the dev extras"
> @echo "  make gates        EVERYTHING CI runs: tests + 10 gates. Under three minutes"
> @echo "  make reproduce    the headline number from the committed example runs, offline"
> @echo ""
> @echo "The published figures, each with the command behind it (doctrine rule 6):"
> @echo "  make n1 .. n6 RUN=example-sequential|example-concurrent   the six numbers"
> @echo "  make honesty-curve     what the headline did as the instrument stopped being blind"
> @echo "  make argument-shapes   how much of a tool surface is attributable, from schemas alone"
> @echo "  make backstop RUN=...  outbound SYNs per destination: what the proxy could NOT see"
> @echo "  make fp / ksweep / inventory / rarity   the calibration block (docs/CALIBRATION.md)"
> @echo "  make words             the documentation budget: findings against rules of operation"
> @echo ""
> @echo "The gates, individually:"
> @echo "  make verify claims-check figures-check corpus-check lint types cov"
> @echo ""
> @echo "Needs Docker and network (a NEW capture, never required to read a number):"
> @echo "  make run / run-concurrent / bench / control"
> @echo ""
> @echo "Two targets exit NON-ZERO as a result, not as a failure: rarity and control."

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
# Writes runs/<timestamp>-sequential/flows.jsonl. See docs/PROTOCOL.md and docs/PROTOCOL.md.
run:
> python3 -m mcpfanout.cli run --registry registry/servers.yaml --out runs/ --pass sequential

# Phase B, CONCURRENT pass: waves of N calls in flight per server, from corpus/concurrent/, with N
# on the bench's own ladder (2, 5, 10) capped per server. This is the ONLY pass number 5 may be
# read from: with one call in flight the strongest grade is unreachable by construction.
# A separate run and a separate figure, never merged with the sequential one (docs/PROTOCOL.md).
run-concurrent:
> python3 -m mcpfanout.cli run --registry registry/servers.yaml --out runs/ --pass concurrent

# F2: the structural matcher's predictions (docs/PREREG-F2.md), on CALIBRATION material.
# This is the one to look at while working. It re-derives sections 4 and 5 of the
# pre-registration, which is the rule 6 debt that document declared.
f2:
> @python3 tools/measure_f2.py

# F2 on the RESERVED half. Measured ONCE, at the end, and its figure is what gets published.
# A separate target from `f2` on purpose: a single command that could be pointed at either half
# is a command somebody points at the wrong one, which is how the previous reserve was lost.
f2-reserved:
> @python3 tools/measure_f2.py --reserved

# The negative corpus's generated halves, re-derived. Fails if either was edited by hand.
corpus-check:
> python3 tools/build_negative_extras.py --check

# Outbound TCP SYNs per destination from a run's pcap backstop. The evidence behind threat 6:
# a client that ignores HTTP(S)_PROXY is invisible to the proxy and visible only here.
backstop:
> @python3 tools/pcap_syns.py --run $(RUN)

# The honesty curve: the headline figure at each stage of the instrument becoming less blind.
# Every observability fix lowered it. That shape is the write-up's argument about method.
honesty-curve:
> @python3 tools/honesty_curve.py

# The documentation's own budget: how many words are measured findings and how many are rules of
# operation and front matter. Declared in docs/README.md and gated by tests/test_word_budget.py,
# because the cheapest way to hit a total word count is to delete evidence, and a declared split
# is worth more than a reached total. Rule 6 applied to a number ABOUT the documents.
words:
> @python3 tools/word_budget.py --summary

# The argument-shape distribution over every probed tool schema. Turns the paper's most
# actionable claim from qualitative into measured. Reads registry/probes/ only, no run needed.
argument-shapes:
> @python3 tools/argument_shapes.py

# Every target whose whole output is JSON is written with `@`, so the recipe line is not echoed
# into the JSON. The command is not lost: each aggregate carries its own `command` field, which is
# rule 6's requirement and survives being piped, saved or quoted somewhere else.
# All six numbers from a run (default: the committed example run, see RUN above).
numbers:
> @python3 -m mcpfanout.cli aggregate --run $(RUN) --number all

n1:
> @python3 -m mcpfanout.cli aggregate --run $(RUN) --number 1
n2:
> @python3 -m mcpfanout.cli aggregate --run $(RUN) --number 2
n3:
> @python3 -m mcpfanout.cli aggregate --run $(RUN) --number 3
n4:
> @python3 -m mcpfanout.cli aggregate --run $(RUN) --number 4
n5:
> @python3 -m mcpfanout.cli aggregate --run $(RUN) --number 5
n6:
> @python3 -m mcpfanout.cli aggregate --run $(RUN) --number 6

# Phase A bench: build the instrument's own measurement. Needs Docker and network.
# Gate rule 8: this must pass before any phase B figure is published.
bench:
> python3 -m mcpfanout.cli run --bench --out runs/

# The instrument block from a bench run: capture recall, attribution precision, false provenance.
bench-verify:
> @python3 -m mcpfanout.cli bench-verify --run $(RUN)

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
> @python3 -m mcpfanout.cli disclosure-check --run $(RUN)

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
# itself (docs/PROTOCOL.md, rules 1 and 4). Counts only: no host, no server id, no digest.
figures:
> python3 -m mcpfanout.cli figures --run $(RUN) --out docs/figures

# ---------------------------------------------------------------------------------------------
# The gates. Every one of them caught something that the suite, as it stood, could not see.
# Gate rule 10: an instrument needs a test that goes red when the instrument is ABSENT.
# CONTRIBUTING.md says what each gate caught and how to run it while working.
# ---------------------------------------------------------------------------------------------

# Gate 2: no figure in the README that disagrees with the artifact it is quoted from, and no figure
# read from the pass that may not publish it. This is what caught numbers 1 and 2 being published
# from the concurrent pass, where the maximum is a statement about our own wave size: the README
# said max 1 and the sequential figure, which is the one allowed to answer, says 84.
claims-check:
> python3 -m pytest tests/test_readme_claims.py tests/test_docstring_figures.py -q

# Gate 3: every calibration artifact, regenerated from the corpus it describes, must come back
# byte for byte. A test that inspects the SHAPE of a committed figure passes just as happily when
# the figure is eight commits stale, which is exactly what happened: the negative corpus gained a
# fifth family and four figures plus three documents went on quoting the old curve while the suite
# stayed green. Regenerating is the only check that can tell the difference.
#
# The SVGs are in here for the same reason: a picture is a published figure, and one drawn by hand
# goes stale in silence.
figures-check:
> $(MAKE) fp fp-calibration ksweep inventory
# `rarity` exits 1 BY DESIGN: the weighting did not lower the rate and the exit code is that
# result. The leading `-` keeps the figure regenerated without turning a measured verdict into a
# broken build, and the verdict itself is asserted by tests/test_rarity.py instead.
> -$(MAKE) rarity
> $(MAKE) curve-svg chain-svg
> git diff --exit-code docs/figures/
# A regenerated figure that is NEW is invisible to `git diff`, and an uncommitted figure is a
# published number nobody can re-derive. Untracked files under docs/figures/ fail the gate too.
> @test -z "$$(git ls-files --others --exclude-standard docs/figures/)" || { \
>   echo "untracked figures under docs/figures/:"; \
>   git ls-files --others --exclude-standard docs/figures/; exit 1; }

# The honesty curve as an image, from the same command that publishes it as JSON.
curve-svg:
> python3 tools/render_honesty_curve.py > docs/figures/honesty-curve.svg

# The observation chain: what an environment-variable proxy sees, and what goes straight past it.
chain-svg:
> python3 tools/render_chain_diagram.py > docs/figures/observation-chain.svg

# Lint, types and coverage. Declared as gates rather than as habits: a threshold nobody enforces
# is a number that only moves in one direction.
lint:
> ruff check .

types:
> mypy src/mcpfanout

cov:
> python3 -m pytest --cov=src/mcpfanout --cov-report=term-missing --cov-fail-under=85 -q
> python3 -m pytest --cov=tools --cov-report=term-missing --cov-fail-under=60 -q

# Gate 6: the headline number, end to end, from the committed example runs. No Docker, no
# network, no credentials. This is the twenty-minute test: a reader who types one command gets
# 0.6579 out of the repository rather than out of a sentence in the README.
reproduce:
> $(MAKE) numbers RUN=example-concurrent
> $(MAKE) n1 RUN=example-sequential
> $(MAKE) n2 RUN=example-sequential
> $(MAKE) honesty-curve
> $(MAKE) argument-shapes

# Everything CI runs, in the order CI runs it. One command, so "it passes locally" means the same
# thing as "it passes on the push".
gates:
> $(MAKE) verify claims-check figures-check corpus-check reproduce lint types cov
> $(MAKE) f2 > /dev/null && $(MAKE) f2-reserved > /dev/null
> @echo "every gate green. The same list runs in .github/workflows/ci.yml."

clean:
> rm -rf build dist src/*.egg-info .pytest_cache
> find . -type d -name __pycache__ -prune -exec rm -rf {} +
