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
 && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# NODE 24, AND THE REASON IS A MEASUREMENT DEFECT, not a preference for a newer runtime.
#
# The capture is a terminating proxy selected by HTTP(S)_PROXY, so interception depends on each
# client choosing to honour those variables. Node's global `fetch` (undici) DOES NOT honour them
# by default. The image shipped Node 20, where there is no way to make it: a server built on
# global fetch reached its API and left nothing in flows.jsonl while every tool call succeeded and
# returned the API's own answers. Measured on run 20260919T193121Z-concurrent: 10 outbound SYNs
# straight to api.github.com in the pcap backstop, zero flows for that server.
#
# Node gained proxy support for global fetch in 22.21.0 and 24.5.0, still OFF by default, enabled
# by NODE_USE_ENV_PROXY=1 or --use-env-proxy. So the fix is one variable and a runtime new enough
# to have it, which is why the base moves from 20 to 24. See docs/THREATS.md threat 19.
#
# The assertion is not decoration. An older Node accepts the variable silently, ignores it, and
# produces a capture that looks exactly like a correct one with a server that egressed nothing:
# gate rule 10's failure mode, in a base image. Build must fail instead.
RUN node -e "const [maj,min]=process.versions.node.split('.').map(Number);     const ok = (maj>24) || (maj===24&&min>=5) || (maj===22&&min>=21);     if(!ok){console.error('Node '+process.versions.node+' has no NODE_USE_ENV_PROXY; need >=22.21 or >=24.5');process.exit(1);}     console.log('node '+process.versions.node+' supports NODE_USE_ENV_PROXY')"

# Turn it on for every process in the container. It is inert without HTTP(S)_PROXY set, so the
# unproxied warm launch is unaffected, and the driver's subprocess env is built from os.environ so
# it reaches each server.
#
# WHAT THIS DOES NOT COVER, and the pcap remains the judge rather than this line: it applies to
# global fetch and undici. A client using node:https directly, or constructing its own agent, or
# pinning certificates, still bypasses the proxy. `make backstop` counts outbound SYNs per
# destination and is what says whether anything is still blind.
ENV NODE_USE_ENV_PROXY=1

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
# capture records the destination host and not the port. See bench/server.py and docs/PROTOCOL.md.
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
