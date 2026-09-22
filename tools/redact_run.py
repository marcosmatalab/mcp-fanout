"""Turn a captured run into a publishable one, so the six numbers reproduce in a clean clone.

    python3 tools/redact_run.py --run runs/20260919T115452Z-sequential --out runs/example-sequential

WHY THIS EXISTS. Gate rule 4 said: never commit a run. The reason was never the file size, it was
that a run states, per server, exactly where that server went and when, which is the who-calls-whom
dataset the README says this project does not publish, and gate rule 3 forbids a server, host or
organisation name in anything published. The cost of that rule was that `make n1` failed in a fresh
clone and five of the ten Quickstart commands did not run, which is a bad trade for a repository
whose argument is reproducibility: a reviewer types the command the table puts in front of them
before reading the paragraph that explains why it cannot work.

WHAT IT REPLACES, and what it deliberately does not:

  server ids       -> server-0 .. server-N, in the order the run's own manifest recorded, which is
                      the registry order. An index, not a name.
  tool names       -> tool-0 .. tool-M within each server, assigned in sorted order.
  call ids         -> <server label>-c<NNN>, keeping the numbering so the join to flows survives.
  destination hosts-> one stable label per class: package-registry-a.., third-party-a.., and
                      loopback-proxy for the proxy itself.
  destination IPs  -> 192.0.2.0/24, the RFC 5737 documentation range, one address per label.
  error text       -> the exception class and the JSON-RPC code, never the message: two of the
                      three errors in these runs name a vendor's environment variable or quote a
                      vendor's validation message.
  digests          -> KEPT, byte for byte. They are salted digests of material that is committed
                      in this repository; keeping them is what makes the numbers identical rather
                      than merely similar.
  timestamps       -> KEPT. They are relative within a run and the run ids are already public.

WHAT IT CARRIES, AND WHY THAT IS A REAL COST. Three of the six numbers are computed by applying a
list in registry/ to a hostname: is this host package infrastructure (numbers 1 and 5), and is it
self-hostable (number 6). A redacted run has no hostname, so those answers cannot be re-derived
from it. They are therefore computed HERE, before the hostnames are destroyed, and carried in the
record (`Flow.dest_class`, `Flow.node_category`) with the digest of every list they were computed
against recorded in the manifest. The cost is that a newer list cannot re-answer an old published
run, which is exactly the property the attribution grade is kept OUT of the record to preserve.
The mitigation is not a promise: `aggregate` reports the carried digest next to the current one, so
a list that has moved shows up in the output instead of being silently assumed.

The same applies to gate rule 7. The declaration in registry/declared-destinations.json is keyed by
real server ids and phrased in terms of what a server's documentation says, neither of which
survives redaction. So the declaration itself is relabelled through the SAME map and carried with
the run, its prose replaced by a pointer. The check then runs for real over the labels, and because
the map is injective the answer is the answer it gives on the capture. What it is not is a fresh
reading of anybody's documentation, and the output says so.

THE PCAP is rewritten rather than trimmed: every SYN becomes a minimal, well-formed packet with a
documentation-range destination, no payload, and the original timestamp and port. The counts per
destination are what `make backstop` publishes and they are preserved exactly, which is what keeps
threat 19's evidence (ten connections the proxy never saw) checkable in a clone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mcpfanout import record as _record
from mcpfanout.classify import PACKAGE_INFRASTRUCTURE_PATH, ExclusionList
from mcpfanout.disclosure import DECLARED_DESTINATIONS_PATH

REPO = Path(__file__).resolve().parent.parent

LOOPBACK_LABEL = "loopback-proxy"
DOC_NET = "192.0.2."          # RFC 5737, reserved for documentation. Never routed.
DOC_FIRST = 10                # leaves .1 .. .9 free for anything a reader wants to add

# What the error text is replaced by. The class and the protocol code are the part that carries
# information about the run; the message is the part that carries a vendor's name.
JSONRPC_CODE = re.compile(r"'code':\s*(-?\d+)")


class Redactor:
    """The label maps for one run. Built once so every file sees the same relabelling."""

    def __init__(self, manifest: dict, flows: list[dict], exclusions: ExclusionList | None):
        self.exclusions = exclusions
        # Server order comes from the run's own manifest, which recorded the registry order at
        # capture time. Reading registry/servers.yaml here would need YAML in a path CI runs and
        # would answer with today's registry about yesterday's run.
        ids = list(manifest.get("server_ids") or [])
        for row in flows:
            if row.get("server_id") and row["server_id"] not in ids:
                ids.append(row["server_id"])
        self.servers = {sid: f"server-{i}" for i, sid in enumerate(ids)}
        self.hosts: dict[str, str] = {}
        self.ips: dict[str, str] = {}
        self.classes: dict[str, str] = {}
        self._packages = 0
        self._third_parties = 0
        for row in flows:
            self._label_host(row.get("dest_host", ""), row.get("dest_ip", ""))
        self.tools: dict[tuple[str, str], str] = {}

    # -- hosts ---------------------------------------------------------------------------------

    def _label_host(self, host: str, ip: str) -> str:
        host = (host or "").strip().lower()
        if not host:
            return ""
        if host in self.hosts:
            # A host can answer from several addresses across a run. Every one of them maps to the
            # label's single address, so the pcap and the flows agree on how many destinations
            # there were; a second address slipping through as "unseen" would invent one.
            label = self.hosts[host]
            if ip:
                self.ips.setdefault(ip, self.ips[label])
            return label
        if host in ("localhost", "127.0.0.1", "::1"):
            label, klass, address = LOOPBACK_LABEL, _record.DEST_LOCAL, "127.0.0.1"
        elif self.exclusions is not None and self.exclusions.matches(host):
            label = f"package-registry-{chr(ord('a') + self._packages)}"
            klass, address = _record.DEST_PACKAGE_INFRASTRUCTURE, self._next_address()
            self._packages += 1
        else:
            label = f"third-party-{chr(ord('a') + self._third_parties)}"
            klass, address = _record.DEST_THIRD_PARTY, self._next_address()
            self._third_parties += 1
        self.hosts[host] = label
        self.classes[label] = klass
        if ip:
            self.ips[ip] = address
        self.ips.setdefault(label, address)
        return label

    def _next_address(self) -> str:
        """One address per LABEL, allocated in order, so the range reads as a short list."""
        return f"{DOC_NET}{DOC_FIRST + len(self.classes)}"

    def host(self, host: str) -> str:
        return self.hosts.get((host or "").strip().lower(), "")

    def ip_for_label(self, label: str) -> str:
        return self.ips.get(label, "")

    def ip(self, ip: str) -> str:
        """A captured address becomes a documentation address, consistently across files."""
        if not ip:
            return ""
        if ip.startswith("127.") or ip == "::1":
            return "127.0.0.1"
        if ip not in self.ips:
            # Seen in the pcap but never in a flow: the proxy did not observe it, which is the
            # whole point of the backstop. It still gets a stable documentation address.
            self.ips[ip] = f"{DOC_NET}{200 + sum(1 for k in self.ips if k.startswith('unseen:'))}"
            self.ips[f"unseen:{ip}"] = self.ips[ip]
        return self.ips[ip]

    # -- servers, tools, calls ------------------------------------------------------------------

    def server(self, server_id: str) -> str:
        return self.servers.get(server_id, server_id)

    def learn_tools(self, calls: list[dict]) -> None:
        by_server: dict[str, set[str]] = {}
        for call in calls:
            by_server.setdefault(call["server_id"], set()).add(call.get("tool_name", ""))
        for server_id, names in by_server.items():
            for index, name in enumerate(sorted(names)):
                self.tools[(server_id, name)] = f"tool-{index}"

    def tool(self, server_id: str, name: str) -> str:
        return self.tools.get((server_id, name), "tool-x")

    def call(self, call_id: str | None) -> str | None:
        if not call_id:
            return call_id
        for server_id, label in self.servers.items():
            if call_id.startswith(server_id + "-"):
                return label + call_id[len(server_id):]
        return call_id


def _scrub_error(text: str) -> str:
    """Keep what the error says about the run, drop what it says about the vendor."""
    if not text:
        return ""
    kind = text.split(":", 1)[0].strip()
    code = JSONRPC_CODE.search(text)
    if code:
        return f"{kind}: tools/call error, JSON-RPC code {code.group(1)}, message redacted"
    return f"{kind}: message redacted"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def redact_flows(flows: list[dict], red: Redactor) -> list[dict]:
    out = []
    for row in flows:
        label = red.host(row.get("dest_host", ""))
        new = dict(row)
        new["server_id"] = red.server(row.get("server_id", ""))
        new["call_id"] = red.call(row.get("call_id"))
        new["dest_host"] = label
        new["dest_ip"] = red.ip_for_label(label) if label else ""
        new["run_id"] = red.run_id
        new["dest_class"] = red.classes.get(label, "")
        out.append(new)
    return out


def redact_calls(calls: list[dict], red: Redactor) -> list[dict]:
    out = []
    for row in calls:
        server_id = row.get("server_id", "")
        new = dict(row)
        new["server_id"] = red.server(server_id)
        new["call_id"] = red.call(row.get("call_id"))
        new["tool_name"] = red.tool(server_id, row.get("tool_name", ""))
        new["error"] = _scrub_error(row.get("error", ""))
        new["run_id"] = red.run_id
        out.append(new)
    return out


def carried_declaration(red: Redactor) -> dict:
    """registry/declared-destinations.json, relabelled through the same map.

    Relabelled and not replayed: the check still runs, over labels, and an injective relabelling
    of both sides of a set comparison gives the same answer. What is dropped is the prose, which
    describes a named server's documented purpose and would re-identify the label it sits on.
    """
    path = REPO / DECLARED_DESTINATIONS_PATH
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    servers = {}
    for server_id, decl in data.get("servers", {}).items():
        label = red.servers.get(server_id)
        if label is None:
            continue
        servers[label] = {
            "call_supplied": decl.get("call_supplied", False),
            "hosts": sorted({red.host(h) for h in decl.get("hosts", []) if red.host(h)}),
            "known_undeclared": {
                red.host(h): "carried from the declaration; the finding is in "
                             "docs/DISCLOSURE-LOG.md"
                for h in decl.get("known_undeclared", {}) if red.host(h)},
            "basis": "relabelled from the committed declaration; the basis names the server and "
                     "is therefore not carried",
            "launch_tool": decl.get("launch_tool", ""),
        }
    return {"list_name": data.get("list_name", ""), "version": data.get("version", ""),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "path": DECLARED_DESTINATIONS_PATH, "servers": servers}


def redact_manifest(manifest: dict, red: Redactor, source_run: str) -> dict:
    out = dict(manifest)
    out["run_id"] = red.run_id
    out["server_ids"] = [red.server(s) for s in manifest.get("server_ids", [])]
    out["server_protocol_versions"] = {
        red.server(s): v for s, v in (manifest.get("server_protocol_versions") or {}).items()}
    out["servers_expecting_egress"] = [red.server(s)
                                       for s in manifest.get("servers_expecting_egress", [])]
    out["credential_presence"] = {
        red.server(s): {f"secret-{i}": bool(v) for i, v in enumerate(secrets.values())}
        for s, secrets in (manifest.get("credential_presence") or {}).items()}
    # Version pins identify a server on their own: three of these ten are the only packages at
    # their exact version. The fact that the run was pinned is kept, the pins are not.
    out["tool_versions"] = {"note": "pinned at capture; the pins identify the servers and are in "
                                    "registry/servers.yaml, not here"}
    out["notes"] = (
        f"REDACTED example run, derived from {source_run} by tools/redact_run.py. Committed so the "
        f"six numbers reproduce in a clean clone with no Docker, no network and no credentials. "
        f"Server ids are indices, tool names are indices, destinations are class labels and "
        f"addresses are RFC 5737 documentation addresses. See runs/README.md.")
    out["redaction"] = {
        "source_run_id": source_run,
        "tool": "tools/redact_run.py",
        "package_infrastructure_sha256": red.exclusions.sha256 if red.exclusions else "",
        "package_infrastructure_path": PACKAGE_INFRASTRUCTURE_PATH,
        "destination_labels": sorted(red.classes),
        "declared_destinations": carried_declaration(red),
        "what_was_kept": "salted digests, byte counts, timestamps, protocol revisions, phases, "
                         "grades' inputs and every field the six numbers are computed from",
        "what_was_replaced": "server ids, tool names, call ids, destination hosts, destination "
                             "addresses and error messages",
    }
    return out


# -- the pcap ----------------------------------------------------------------------------------

def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _syn_packet(src: str, dst: str, sport: int, dport: int) -> bytes:
    """A minimal, well-formed IPv4 TCP SYN with no payload and correct checksums."""
    src_b = bytes(int(p) for p in src.split("."))
    dst_b = bytes(int(p) for p in dst.split("."))
    tcp = struct.pack("!HHIIBBHHH", sport, dport, 0, 0, 5 << 4, 0x02, 64240, 0, 0)
    pseudo = src_b + dst_b + struct.pack("!BBH", 0, 6, len(tcp))
    tcp = tcp[:16] + struct.pack("!H", _checksum(pseudo + tcp)) + tcp[18:]
    ip = struct.pack("!BBHHHBBH", 0x45, 0, 20 + len(tcp), 0, 0x4000, 64, 6, 0) + src_b + dst_b
    ip = ip[:10] + struct.pack("!H", _checksum(ip)) + ip[12:]
    return ip + tcp


def rewrite_pcap(source: Path, out: Path, red: Redactor) -> dict:
    """Rebuild the backstop as SYNs only, with documentation addresses. Counts are preserved."""
    from pcap_syns import L2_LEN

    data = source.read_bytes()
    magic = data[:4]
    endian = "<" if magic == b"\xd4\xc3\xb2\xa1" else ">"
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    l2 = L2_LEN[linktype]
    # The rewritten file is Ethernet (linktype 1) with a zeroed link header. The captured link
    # layer is LINUX_SLL2, which carries interface indices and address fields that say nothing
    # about the finding and would have to be redacted in turn; Ethernet with zeros carries
    # nothing at all and is the one link type every reader handles without a flag.
    header = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    l2_out = b"\x00" * 12 + b"\x08\x00"
    packets: list[bytes] = []
    kept = 0
    off = 24
    while off + 16 <= len(data):
        ts_sec, ts_usec, caplen, _ = struct.unpack(endian + "IIII", data[off:off + 16])
        off += 16
        pkt = data[off:off + caplen]
        off += caplen
        ip = pkt[l2:]
        if len(ip) < 20 or (ip[0] >> 4) != 4 or ip[9] != 6:
            continue
        tcp = ip[(ip[0] & 0xF) * 4:]
        if len(tcp) < 14 or not (tcp[13] & 0x02) or tcp[13] & 0x10:
            continue
        sport, dport = struct.unpack("!HH", tcp[0:4])
        src = red.ip(".".join(str(b) for b in ip[12:16]))
        dst = red.ip(".".join(str(b) for b in ip[16:20]))
        body = l2_out + _syn_packet(src or "192.0.2.1", dst, sport, dport)
        packets.append(struct.pack("<IIII", ts_sec, ts_usec, len(body), len(body)) + body)
        kept += 1
    out.write_bytes(header + b"".join(packets))
    return {"syns": kept, "bytes": out.stat().st_size, "source_bytes": len(data)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="the captured run directory to redact")
    ap.add_argument("--out", required=True, help="where to write the redacted run")
    args = ap.parse_args()

    run_dir = Path(args.run)
    out_dir = Path(args.out)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    flows = _read_jsonl(run_dir / "flows.jsonl")
    calls = _read_jsonl(run_dir / "calls.jsonl")
    waves = _read_jsonl(run_dir / "waves.jsonl")

    exclusions = ExclusionList.load(REPO / PACKAGE_INFRASTRUCTURE_PATH)
    if exclusions is None:
        raise SystemExit(f"{PACKAGE_INFRASTRUCTURE_PATH} is missing: the package-infrastructure "
                         f"classification cannot be computed, and a redacted run without it "
                         f"would publish numbers 1 and 5 against an empty list")
    red = Redactor(manifest, flows, exclusions)
    red.run_id = out_dir.name
    red.learn_tools(calls)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(redact_manifest(manifest, red, manifest["run_id"]), indent=2, sort_keys=True)
        + "\n", encoding="utf-8")
    _write_jsonl(out_dir / "calls.jsonl", redact_calls(calls, red))
    _write_jsonl(out_dir / "flows.jsonl", redact_flows(flows, red))
    if waves:
        _write_jsonl(out_dir / "waves.jsonl",
                     [{**w, "server_id": red.server(w["server_id"])} for w in waves])
    summary = {"run": red.run_id, "servers": len(red.servers), "flows": len(flows),
               "calls": len(calls), "destination_labels": red.classes}
    pcap = run_dir / "backstop.pcap"
    if pcap.is_file():
        summary["backstop"] = rewrite_pcap(pcap, out_dir / "backstop.pcap", red)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
