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

import hashlib
import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path

LOCAL = "local"
SELF_HOSTABLE = "self_hostable"
REMOTE_LEAF = "remote_leaf"

# Where the package-infrastructure exclusion list lives. Number 1 publishes a connection count
# that excludes these hosts alongside the raw count that includes them (see ExclusionList).
PACKAGE_INFRASTRUCTURE_PATH = "registry/package-infrastructure.json"

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


@dataclass(frozen=True)
class ExclusionList:
    """A declared, published, versioned set of host suffixes that a number may exclude.

    Three properties make this an exclusion list rather than a silent filter, and all three are
    load-bearing:

    1. It is DATA IN THE REPOSITORY, not code. One file, committed, with a version string. There
       are deliberately NO embedded defaults: defaults would mean the effective list is only
       half in registry/, which would make the citation below a half-truth. If the file is
       missing, the excluded figure is not computed at all and says why -- never silently
       computed against an empty list, which would look identical to "no package traffic".
    2. The RAW COUNT IS NEVER DISCARDED. Whatever excludes, excludes alongside the unfiltered
       figure, so a server with real fan-out to a listed host stays visible.
    3. The output CITES IT by name, version and sha256 (see ``citation``), so a reader can check
       exactly which list produced a figure. The citation carries no hostnames, because gate
       rule 3 forbids a host in published output; the digest plus the committed file is what
       makes the list checkable without naming anything in the aggregate.
    """
    name: str
    version: str
    suffixes: tuple[str, ...]
    sha256: str
    path: str

    @classmethod
    def load(cls, path: str | Path) -> "ExclusionList | None":
        """Load the list, or None if the file is absent. Absent is reported, never assumed empty."""
        p = Path(path)
        if not p.is_file():
            return None
        raw = p.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        return cls(
            name=data.get("list_name", p.stem),
            version=data.get("version", ""),
            suffixes=tuple(data.get("suffixes", ())),
            sha256=hashlib.sha256(raw).hexdigest(),
            path=str(path),
        )

    def matches(self, host: str) -> bool:
        return _suffix_match(host or "", self.suffixes)

    def citation(self) -> dict:
        """What goes into the aggregate output. Counts and identifiers only, never a hostname.

        The path is published as the canonical repository-relative one (parent directory plus
        file name), NOT as whatever the caller passed. A caller that loads by absolute path would
        otherwise publish the operator's home directory into the aggregate -- the same class of
        leak as a probe file naming /home/<user>, and gate rule 3 territory.
        """
        p = Path(self.path)
        return {"list_name": self.name, "version": self.version,
                "path": f"{p.parent.name}/{p.name}" if p.parent.name else p.name,
                "sha256": self.sha256, "suffix_count": len(self.suffixes)}
