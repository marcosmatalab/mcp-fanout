"""Number 6: is a touched third party itself self-hostable, or a remote leaf?

Number 6 sizes the recursion of docs/METHOD.md. The edge observer can advance one hop at a
time only over nodes it can also host. A node that is itself a self-hostable MCP server (an
npm/pip package we can run in our own container) is recursable interior; a hosted SaaS API is a
leaf where the chain breaks. Number 6 is (local + self_hostable) / distinct_nodes.

Classification decisions
------------------------
- Conservative default: an unknown public domain is treated as a remote leaf, NOT self-hostable.
  Reason: claiming a node is self-hostable when it is not would inflate the recursion's reach,
  which is the reachable-depth claim the whole product rests on. The safe direction is to
  under-claim reach, so "unknown" counts against self-hostability. The breakdown is reported so
  the unknown share is visible and can be curated down over time.
- Loopback and RFC1918 private addresses count as local: they are on our own side of the fence
  by definition, the deepest form of self-hostable.
- The registry is data, not code: default suffixes are embedded so classification works with no
  file, and an optional JSON registry (registry/selfhostable.json) extends them. JSON, not YAML,
  so this module stays in the standard library and the aggregation path pulls no dependency.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

LOCAL = "local"
SELF_HOSTABLE = "self_hostable"
REMOTE_LEAF = "remote_leaf"

# Default remote-leaf suffixes: hosted APIs that cannot be run on our own machine. Starter set,
# meant to grow through the registry file, never claimed to be exhaustive.
_DEFAULT_REMOTE_LEAF_SUFFIXES = (
    "googleapis.com", "google.com",
    "api.openai.com", "api.anthropic.com",
    "api.stripe.com", "api.github.com", "githubusercontent.com",
    "amazonaws.com", "blob.core.windows.net", "azure.com",
    "slack.com", "atlassian.net", "atlassian.com",
    "notion.so", "notion.com",
    "api.brave.com", "duckduckgo.com", "bing.com",
)


@dataclass(frozen=True)
class Registry:
    remote_leaf_suffixes: tuple[str, ...] = _DEFAULT_REMOTE_LEAF_SUFFIXES
    self_hostable_suffixes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> "Registry":
        """Build from a parsed JSON dict, extending the embedded defaults (never shrinking them)."""
        if not data:
            return cls()
        extra_remote = tuple(data.get("remote_leaf_suffixes", ()))
        self_hostable = tuple(data.get("self_hostable_suffixes", ()))
        return cls(
            remote_leaf_suffixes=_DEFAULT_REMOTE_LEAF_SUFFIXES + extra_remote,
            self_hostable_suffixes=self_hostable,
        )


def _is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _suffix_match(host: str, suffixes: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == s or host.endswith("." + s) for s in suffixes)


def classify_host(host: str, registry: Registry | None = None) -> str:
    """Classify one destination host into local / self_hostable / remote_leaf."""
    registry = registry or Registry()
    host = (host or "").strip().lower()
    if host in ("localhost", "127.0.0.1", "::1", "") or _is_private_ip(host):
        return LOCAL
    if _suffix_match(host, registry.self_hostable_suffixes):
        return SELF_HOSTABLE
    if _suffix_match(host, registry.remote_leaf_suffixes):
        return REMOTE_LEAF
    # Unknown public domain: conservative, counts as a leaf. See module docstring.
    return REMOTE_LEAF


def selfhostable_fraction(hosts: set[str], registry: Registry | None = None) -> tuple[float, dict[str, int]]:
    """Number 6 over a set of distinct destination hosts.

    Returns the fraction that is recursable (local + self_hostable) and the per-category counts,
    so the report can show the breakdown rather than a bare ratio. An empty set returns 0.0, not
    an error: no nodes means no reach to size.
    """
    counts = {LOCAL: 0, SELF_HOSTABLE: 0, REMOTE_LEAF: 0}
    for h in hosts:
        counts[classify_host(h, registry)] += 1
    total = sum(counts.values())
    recursable = counts[LOCAL] + counts[SELF_HOSTABLE]
    fraction = (recursable / total) if total else 0.0
    return fraction, counts
