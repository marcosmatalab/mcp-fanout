"""Gate rule 7 as a command: which destinations of a run nobody declared.

Gate rule 7 (docs/THE-GATE.md) says that if a server egresses to a destination its documentation
does not declare, we stop and flag it before publishing anything. Until now that rule was a
sentence, and the way it would be honoured was: read a list of hostnames after a run and
remember which ones are supposed to be there. That works for one server and fails for ten,
silently, in the direction of publishing.

So this module reduces a run's destinations to the set nobody expected, per server, against the
declared list in ``registry/declared-destinations.json``.

WHAT IT DOES NOT DO, and this bound is the point. It does not decide gate rule 7. The declared
set is derived from the committed tool schemas and the packages' stated purpose, NOT from a
reading of each upstream README, and the registry file says so in its own ``_what_basis_means``
field. Asserting what a document says without having read it is exactly the plausible guess this
repository keeps finding in its own history. What the check produces is a short list of hosts to
read documentation ABOUT, which is the part a human cannot do reliably from a hostname dump.

Three outcomes, never two:

    clear                 every observed host is declared, or is a known, already written up
                          exception
    review_required       at least one host is new, or a server has no declaration at all
    undeterminable        the declaration file is missing, so nothing may be concluded either way

"undeterminable" exists for the same reason ``provenance_unknown`` does: "we looked and found
nothing" and "we could not look" are different findings, and collapsing them is how a blind spot
reads as a clean result.

THIS OUTPUT IS OPERATOR-ONLY. It names servers and hostnames, which gate rule 3 forbids in
anything published. It is written into the run directory, which is gitignored, and never into
docs/figures/. That is the same division everything else here uses: the run keeps identifying
detail, the published artifact keeps counts.

Standard library only, like the rest of the measurement core: the declaration is JSON rather than
YAML precisely so this module and the CLI that calls it pull no dependency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .classify import matches_suffix

DECLARED_DESTINATIONS_PATH = "registry/declared-destinations.json"

# A flow whose server could not be identified (egress seen while no call was in flight, so the
# control file named nobody). Bucketed under its own key rather than dropped: unattributed egress
# to an undeclared host is the most interesting kind, and dropping it would be the one filter
# this project cannot afford.
UNKNOWN_SERVER = "<server-not-identified>"

VERDICT_CLEAR = "clear"
VERDICT_REVIEW = "review_required"
VERDICT_UNDETERMINABLE = "undeterminable"

REASON_NEW_HOST = "destination not declared and not a known exception"
REASON_NO_DECLARATION = "no declaration exists for this server, so nothing is declared for it"


@dataclass(frozen=True)
class ServerDeclaration:
    """What one server is expected to reach, and on what basis."""
    server_id: str
    call_supplied: bool
    hosts: tuple[str, ...]
    known_undeclared: dict          # host -> the document that carries the finding
    basis: str

    def status_of(self, host: str) -> str:
        """declared / known / new for one observed host."""
        if matches_suffix(host, self.hosts):
            return "declared"
        if matches_suffix(host, tuple(self.known_undeclared)):
            return "known"
        return "new"


@dataclass(frozen=True)
class DeclaredDestinations:
    name: str
    version: str
    sha256: str
    path: str
    servers: dict[str, ServerDeclaration]

    @classmethod
    def load(cls, path: str | Path = DECLARED_DESTINATIONS_PATH) -> "DeclaredDestinations | None":
        """Load the declaration, or None if the file is absent. Absent is reported, not assumed."""
        p = Path(path)
        if not p.is_file():
            return None
        raw = p.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        servers = {
            sid: ServerDeclaration(
                server_id=sid,
                call_supplied=bool(entry.get("call_supplied", False)),
                hosts=tuple(entry.get("hosts", ())),
                known_undeclared=dict(entry.get("known_undeclared", {})),
                basis=entry.get("basis", ""),
            )
            for sid, entry in data.get("servers", {}).items()
        }
        return cls(name=data.get("list_name", p.stem), version=data.get("version", ""),
                   sha256=hashlib.sha256(raw).hexdigest(), path=str(path), servers=servers)

    def citation(self) -> dict:
        """Identifiers only, so the citation can travel even where hostnames may not."""
        p = Path(self.path)
        return {"list_name": self.name, "version": self.version,
                "path": f"{p.parent.name}/{p.name}" if p.parent.name else p.name,
                "sha256": self.sha256, "server_count": len(self.servers)}


def check(flows, declared: DeclaredDestinations | None) -> dict:
    """Compare a run's observed destinations against the declaration. Operator-only output.

    ``flows`` is any iterable of records with ``server_id`` and ``dest_host`` (a run's
    ``flows.jsonl`` read back as ``Flow``). Connections with no host, which is what a
    non-HTTP flow looks like, are counted separately rather than treated as a destination:
    "we could not see where it went" is not "it went nowhere".
    """
    by_server: dict[str, set[str]] = {}
    hostless = 0
    for f in flows:
        host = (getattr(f, "dest_host", "") or "").strip().lower()
        if not host:
            hostless += 1
            continue
        by_server.setdefault(getattr(f, "server_id", "") or UNKNOWN_SERVER, set()).add(host)

    if declared is None:
        return {
            "_operator_only": ("names servers and hostnames; gate rule 3 forbids publishing this "
                               "file or quoting a hostname from it"),
            "verdict": VERDICT_UNDETERMINABLE,
            "reason": (f"{DECLARED_DESTINATIONS_PATH} is missing, so no destination can be called "
                       f"declared or undeclared. Gate rule 7 is unevaluated, which is not the "
                       f"same as satisfied"),
            "declaration": None,
            "servers": {sid: {"observed_hosts": sorted(hosts)} for sid, hosts in sorted(by_server.items())},
            "connections_without_a_host": hostless,
        }

    servers: dict[str, dict] = {}
    review: list[str] = []
    for sid, hosts in sorted(by_server.items()):
        decl = declared.servers.get(sid)
        if decl is None:
            servers[sid] = {"observed_hosts": sorted(hosts), "declared": [], "known": [],
                            "new": sorted(hosts), "reason": REASON_NO_DECLARATION}
            review.append(sid)
            continue
        buckets: dict[str, list[str]] = {"declared": [], "known": [], "new": []}
        for host in sorted(hosts):
            buckets[decl.status_of(host)].append(host)
        servers[sid] = {
            "observed_hosts": sorted(hosts),
            **buckets,
            "known_references": {h: decl.known_undeclared[k]
                                 for h in buckets["known"]
                                 for k in decl.known_undeclared
                                 if matches_suffix(h, (k,))},
            "basis": decl.basis,
        }
        if buckets["new"]:
            servers[sid]["reason"] = REASON_NEW_HOST
            review.append(sid)

    verdict = VERDICT_REVIEW if review else VERDICT_CLEAR
    return {
        "_operator_only": ("names servers and hostnames; gate rule 3 forbids publishing this file "
                           "or quoting a hostname from it"),
        "verdict": verdict,
        "servers_to_review": sorted(review),
        "gate_rule_7": (
            "STOP. Before publishing any figure from this run, read the documentation of each "
            "server listed in servers_to_review for the hosts under its 'new' key, and decide "
            "whether that destination is declared there. If it is not, the finding is disclosed "
            "responsibly first and nothing that locates the server is published until then."
            if verdict == VERDICT_REVIEW else
            "Every observed destination is declared, or is a known exception with a written-up "
            "finding behind it. This is not a proof that the documentation declares it: the "
            "declaration is derived from tool schemas and stated purpose, not quoted from a "
            "README (see the registry file's own _what_basis_means)."),
        "declaration": declared.citation(),
        "servers": servers,
        "connections_without_a_host": hostless,
    }
