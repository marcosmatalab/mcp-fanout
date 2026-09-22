"""Gate rule 7 as a command: which destinations of a run nobody declared.

Gate rule 7 (docs/PROTOCOL.md) says that if a server egresses to a destination its documentation
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
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .classify import matches_suffix
from .record import DEST_PACKAGE_INFRASTRUCTURE
from .record import PHASES_NOT_CALL_CAUSED as _PHASES_NOT_CALL_CAUSED

DECLARED_DESTINATIONS_PATH = "registry/declared-destinations.json"

# A flow whose server could not be identified (egress seen while no call was in flight, so the
# control file named nobody). Bucketed under its own key rather than dropped: unattributed egress
# to an undeclared host is the most interesting kind, and dropping it would be the one filter
# this project cannot afford.
UNKNOWN_SERVER = "<server-not-identified>"

VERDICT_CLEAR = "clear"
VERDICT_REVIEW = "review_required"
VERDICT_UNDETERMINABLE = "undeterminable"

# Commands that RESOLVE A PACKAGE and then exec the real server. For these, the subprocess we spawn
# is the launcher, so a connection made before the first tool call, to a host on the declared
# package-infrastructure list, is the launcher's traffic and not the server's. Both conditions are
# required, and both come from declared data: the phase from the driver, the destination from
# registry/package-infrastructure.json. Neither is inferred from a hostname's appearance.
PACKAGE_LAUNCHERS = ("npx", "uvx", "pipx")

REASON_NEW_HOST = "destination not declared and not a known exception"
REASON_PRE_CALL_UNDECLARED = (
    "seen before the first tool call, and NOT declared package infrastructure, so it is the "
    "launched process reaching somewhere on its own at startup")
REASON_NO_DECLARATION = "no declaration exists for this server, so nothing is declared for it"


@dataclass(frozen=True)
class ServerDeclaration:
    """What one server is expected to reach, and on what basis."""
    server_id: str
    call_supplied: bool
    hosts: tuple[str, ...]
    known_undeclared: dict[str, Any]          # host -> the document that carries the finding
    basis: str
    launch_tool: str = ""           # argv[0] of the launch command; see PACKAGE_LAUNCHERS

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
    def load(cls, path: str | Path = DECLARED_DESTINATIONS_PATH) -> DeclaredDestinations | None:
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
                launch_tool=entry.get("launch_tool", ""),
            )
            for sid, entry in data.get("servers", {}).items()
        }
        return cls(name=data.get("list_name", p.stem), version=data.get("version", ""),
                   sha256=hashlib.sha256(raw).hexdigest(), path=str(path), servers=servers)

    @classmethod
    def carried(cls, block: dict[str, Any]) -> DeclaredDestinations:
        """The declaration a REDACTED run carries, relabelled through the run's own map.

        A redacted run's servers are indices and its destinations are class labels, so the
        committed declaration, which is keyed by server id and phrased in terms of what a named
        server's documentation says, cannot be applied to it. `tools/redact_run.py` relabels both
        sides of the comparison through the same injective map and stores the result in the
        manifest, so the check still RUNS rather than being replayed: relabelling both sides of a
        set comparison cannot change its answer.

        What it is not is a fresh reading of anybody's documentation, and `path` says so, because
        a citation that pointed at registry/declared-destinations.json would claim a check against
        today's file that was in fact made against the file named by the digest below.
        """
        servers = {
            sid: ServerDeclaration(
                server_id=sid,
                call_supplied=bool(entry.get("call_supplied", False)),
                hosts=tuple(entry.get("hosts", ())),
                known_undeclared=dict(entry.get("known_undeclared", {})),
                basis=entry.get("basis", ""),
                launch_tool=entry.get("launch_tool", ""),
            )
            for sid, entry in block.get("servers", {}).items()
        }
        return cls(name=block.get("list_name", "declared-destinations"),
                   version=block.get("version", ""), sha256=block.get("sha256", ""),
                   path=f"carried by the run, relabelled from {block.get('path', '')}",
                   servers=servers)

    def citation(self) -> dict[str, Any]:
        """Identifiers only, so the citation can travel even where hostnames may not."""
        p = Path(self.path)
        return {"list_name": self.name, "version": self.version,
                "path": f"{p.parent.name}/{p.name}" if p.parent.name else p.name,
                "sha256": self.sha256, "server_count": len(self.servers)}


def _sort_destinations(
    flows: Iterable[Any], declared: DeclaredDestinations | None, package_infrastructure: Any,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]], int]:
    """Put every observed destination into one of three piles, before anything is judged.

    The piles are the first branch of gate rule 7's decision procedure, and they are separated
    here rather than inside the judgement so that "whose traffic is this" and "is it declared"
    stay two questions. Returns (launcher destinations, pre-call destinations that are not the
    launcher's, per-server call-caused destinations, connections with no host at all).
    """
    launcher_by_server: dict[str, set[str]] = {}
    pre_call_other: dict[str, set[str]] = {}
    by_server: dict[str, set[str]] = {}
    hostless = 0
    for f in flows:
        host = (getattr(f, "dest_host", "") or "").strip().lower()
        if not host:
            hostless += 1
            continue
        sid = getattr(f, "server_id", "") or UNKNOWN_SERVER
        if getattr(f, "phase", "") in _PHASES_NOT_CALL_CAUSED:
            decl = declared.servers.get(sid) if declared else None
            # Same two paths as aggregate._on_package_infrastructure: a captured run is
            # classified here from its hostname, a redacted one carries the answer because its
            # hostname is gone. Asking the list about a class label would answer "not package
            # infrastructure" for every one of them and send ten servers to review.
            dest_class = getattr(f, "dest_class", "") or ""
            is_package_host = (dest_class == DEST_PACKAGE_INFRASTRUCTURE if dest_class
                               else bool(package_infrastructure
                                         and package_infrastructure.matches(host)))
            launched_by_a_launcher = bool(decl and decl.launch_tool in PACKAGE_LAUNCHERS)
            if is_package_host and launched_by_a_launcher:
                # Branch one of the decision procedure: the launcher's traffic. Recorded apart, no
                # disclosure, and never folded into the server's own destinations.
                launcher_by_server.setdefault(sid, set()).add(host)
            else:
                # Pre-first-call egress that is NOT the package manager resolving a dependency. The
                # process we spawned reached somewhere on its own before any call was made, which is
                # exactly the kind of finding gate rule 7 exists for, so it is reviewed.
                pre_call_other.setdefault(sid, set()).add(host)
            continue
        by_server.setdefault(sid, set()).add(host)

    return launcher_by_server, pre_call_other, by_server, hostless


def _judge_servers(
    by_server: dict[str, set[str]], pre_call_other: dict[str, set[str]],
    declared: DeclaredDestinations,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Per server: declared, known, or new, and which servers that puts under review.

    A server with no declaration at all goes under review rather than passing: the
    absence of an expectation is not the satisfaction of one. Pre-first-call egress that
    is not the package manager's is added afterwards, because it is a finding about the
    same server arriving from a different branch of the procedure.
    """
    servers: dict[str, dict[str, Any]] = {}
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

    for sid, hosts in sorted(pre_call_other.items()):
        entry = servers.setdefault(sid, {"observed_hosts": [], "declared": [], "known": [],
                                         "new": []})
        entry["pre_first_call_undeclared"] = sorted(hosts)
        entry["reason"] = REASON_PRE_CALL_UNDECLARED
        review.append(sid)
    return servers, review


def check(flows: Iterable[Any], declared: DeclaredDestinations | None,
          package_infrastructure: Any = None) -> dict[str, Any]:
    """Compare a run's observed destinations against the declaration. Operator-only output.

    ``flows`` is any iterable of records with ``server_id`` and ``dest_host`` (a run's
    ``flows.jsonl`` read back as ``Flow``). Connections with no host, which is what a
    non-HTTP flow looks like, are counted separately rather than treated as a destination:
    "we could not see where it went" is not "it went nowhere".

    THE LAUNCHER'S DESTINATIONS ARE SEPARATED BEFORE ANYTHING IS CLASSIFIED, which is the first
    branch of gate rule 7's decision procedure: a destination contacted by the launcher before the
    server process exists is not the server's egress, so it is recorded apart and triggers no
    disclosure. `npx -y pkg@ver` resolving a package is npm's traffic, and asking whether the
    SERVER's documentation declares it is asking the wrong party. They are still reported, by host,
    because an operator has to be able to see them; what they do not do is put a server into
    servers_to_review.
    """
    launcher_by_server, pre_call_other, by_server, hostless = _sort_destinations(
        flows, declared, package_infrastructure)
    if declared is None:
        return {
            "_operator_only": ("names servers and hostnames; gate rule 3 forbids publishing this "
                               "file or quoting a hostname from it"),
            "verdict": VERDICT_UNDETERMINABLE,
            "reason": (f"{DECLARED_DESTINATIONS_PATH} is missing, so no destination can be called "
                       f"declared or undeclared. Gate rule 7 is unevaluated, which is not the "
                       f"same as satisfied"),
            "declaration": None,
            "servers": {sid: {"observed_hosts": sorted(hosts)} for sid,
                hosts in sorted(by_server.items())},
            "launcher_destinations": {sid: sorted(hosts)
                                      for sid, hosts in sorted(launcher_by_server.items())},
            "connections_without_a_host": hostless,
        }

    servers, review = _judge_servers(by_server, pre_call_other, declared)
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
        # Reported, never reviewed: gate rule 7's first branch. These are the package manager's
        # destinations, seen before the server process existed, and the server's documentation is
        # not the document that would declare them.
        "launcher_destinations": {sid: sorted(hosts)
                                  for sid, hosts in sorted(launcher_by_server.items())},
        "launcher_note": ("contacted before the first tool call, by a launch command that "
                          "resolves a "
                          "package (npx, uvx), to a host on the declared package-infrastructure "
                          "list: the launcher's traffic and not the server's, recorded apart and "
                          "triggering no disclosure. Both conditions are required and both come "
                          "from declared data"),
        "package_infrastructure_list": (package_infrastructure.citation()
                                        if package_infrastructure else None),
        "connections_without_a_host": hostless,
    }
