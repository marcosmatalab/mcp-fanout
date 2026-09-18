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
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg tcpdump \
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

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[capture]"

# Copy the rest (harness, registry, corpus, docs). Done last so code edits do not bust the layer.
COPY . .

# The proxy port. No server listens on the host; everything is internal to the container.
EXPOSE 8080

ENTRYPOINT ["bash", "harness/run.sh"]
