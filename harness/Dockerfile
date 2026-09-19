# Harness image: everything needed to run one capture inside an isolated container.
#
# Why a container at all: gate rule 5 says nothing runs outside the container and no server is
# started against real credentials. The container is the boundary that makes that true. It also
# gives a clean, throwaway network so a misbehaving server cannot reach a real service of ours.
#
# Base: a slim Python plus Node, because most installed MCP servers ship as npm packages driven
# by npx. uv is added so uvx-style Python servers also run. Versions are pinned loosely here and
# must be frozen (by digest) in registry/servers.yaml before any number is published.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
# git is a MEASUREMENT DEPENDENCY, not a convenience. mcp-server-git drives GitPython, which
# needs the git BINARY: without it the server exits before the JSON-RPC handshake with
# GIT_PYTHON_REFRESH advice on stderr, and the run records "did not start" for a server the
# registry says starts with no credentials. Found on the first ten-server capture, and it also
# exposed that harness/probe.py had been run on the HOST, where git exists, so the registry's
# measured facts came from an environment the capture did not reproduce. Same class of error as
# brave-search's missing key: a server that never starts produces no attempt to watch.
# The headless-Chromium shared libraries, for the same reason git is here: without them
# puppeteer's downloaded Chrome exits with "libglib-2.0.so.0: cannot open shared object file" and
# every call to that server errors, so one of the three egress-capable servers records zero egress
# for a reason that has nothing to do with the server. Measured on the first ten-server capture.
# The list is Chrome's own runtime dependencies on bookworm; `chromium` from apt would pull them in
# too, along with a browser binary puppeteer will not use, so the libraries are named instead.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg tcpdump git \
        libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libxcb1 \
        libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 libx11-6 libxext6 fonts-liberation \
        libnss3-tools \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# uv AND uvx for uvx-launched Python MCP servers. Both binaries, because registry/servers.yaml
# launches fetch, git and time with `uvx` and the installer puts two separate executables in
# ~/.local/bin -- symlinking only `uv` left the image unable to start three of the ten servers
# with FileNotFoundError: 'uvx'. No `|| true` either: that swallowed the failure so the image
# built green and broke at capture time instead, which is the worst place to find out.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && ln -s /root/.local/bin/uv /usr/local/bin/uv \
 && ln -s /root/.local/bin/uvx /usr/local/bin/uvx \
 && uv --version && uvx --version

# Phase A bench destinations. One hostname per call in a bench run, all resolving to loopback,
# so each call has a DISTINCT destination and the comparator can join a truth-ledger row to an
# observed flow exactly. They are separate names rather than one name on many ports because the
# capture records the destination host and not the port. See bench/server.py and docs/PHASES.md.
RUN python3 -c "print('\n'.join('127.0.0.1 sink%03d.bench.invalid' % i for i in range(128)))" \
    >> /etc/hosts.bench \
 && cat /etc/hosts.bench

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[capture]"

# Copy the rest (harness, registry, corpus, docs). Done last so code edits do not bust the layer.
COPY . .

# The proxy port. No server listens on the host; everything is internal to the container.
EXPOSE 8080

ENTRYPOINT ["bash", "harness/run.sh"]
