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

# uv for uvx-launched Python MCP servers.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && ln -s /root/.local/bin/uv /usr/local/bin/uv || true

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[capture]"

# Copy the rest (harness, registry, corpus, docs). Done last so code edits do not bust the layer.
COPY . .

# The proxy port. No server listens on the host; everything is internal to the container.
EXPOSE 8080

ENTRYPOINT ["bash", "harness/run.sh"]
