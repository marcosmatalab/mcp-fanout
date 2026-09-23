"""Count outbound TCP SYNs per destination in a run's backstop pcap. Standard library only.

WHY THIS EXISTS. The proxy sees only clients that honour HTTP(S)_PROXY. Node's global fetch
(undici) does not, so a server using it reaches its API while `flows.jsonl` stays empty for it and
the tool call plainly succeeds (docs/THREATS.md threat 6). The pcap is the only evidence that the
traffic happened at all, and until this file existed the claim rested on an ad-hoc script nobody
could re-run. Rule 6: a number that appears in a threat needs a command behind it.

What it is NOT: reconciliation. It counts connections, it cannot say what was in them, and a SYN
count is not comparable with a flow count (one flow is a request, one SYN is a connection that may
carry many or none). It answers exactly one question: did bytes leave for that host at all.

WHAT IT PRINTS BESIDE THE COUNTS, AND WHY. A SYN count alone does not show the finding: threat 19
is that a server completed its calls while the proxy recorded nothing for it, and the other half of
that sentence lives in calls.jsonl and flows.jsonl, which no command printed. So the output also
carries, from the same run directory:

  unobserved_destinations  SYN destinations whose address appears in no flow, i.e. connections
                           the proxy never saw. Loopback is excluded: that is the proxy itself.
  servers                  per server: calls sent, calls completed, proxy flows, and proxy flows
                           seen while calls were being driven (phase `driving`). Flows from the
                           launcher and handshake phases are counted separately because no call
                           existed yet, so they say nothing about whether the calls were seen.

Deliberately NOT done: pairing a server with a destination. The pcap carries no process identity,
and joining the two by timing would be inference, which this project does not do in its own
diagnostics any more than in the matcher. Both halves are printed and the pairing is left to the
reader, with the evidence for it in docs/THREATS.md threat 19.

    make backstop RUN=runs/<id>
"""

from __future__ import annotations

import argparse
import collections
import json
import struct
import sys
from pathlib import Path

# Link layers we have actually seen out of the harness. Anything else is refused rather than
# guessed: a wrong header offset silently yields zero SYNs, which reads as "nothing left the
# machine" and is gate rule 10's failure mode in a parser.
# DLT_RAW is 0 bytes of link layer, not 4: the IP header starts at byte zero. The 4 belongs to
# DLT_NULL, which prefixes a host-order address-family word. Correcting it rather than leaving it:
# a wrong offset here does not error, it reads the IP header at the wrong place, matches nothing
# and reports zero outbound connections, which is the one answer that reads as a finding.
L2_LEN = {0: 4, 1: 14, 101: 0, 113: 16, 276: 20}   # NULL, EN10MB, RAW, LINUX_SLL, LINUX_SLL2


def syn_counts(path: Path) -> dict:
    data = path.read_bytes()
    magic = data[:4]
    if magic == b"\xd4\xc3\xb2\xa1":
        endian = "<"
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian = ">"
    else:
        raise SystemExit(f"{path}: not a classic pcap (magic {magic.hex()})")
    linktype = struct.unpack(endian + "I", data[20:24])[0]
    if linktype not in L2_LEN:
        raise SystemExit(f"{path}: unsupported linktype {linktype}; refusing to guess an offset")
    l2 = L2_LEN[linktype]

    off, packets = 24, 0
    syns: collections.Counter = collections.Counter()
    while off + 16 <= len(data):
        _, _, caplen, _ = struct.unpack(endian + "IIII", data[off:off + 16])
        off += 16
        pkt = data[off:off + caplen]
        off += caplen
        packets += 1
        ip = pkt[l2:]
        if len(ip) < 20 or (ip[0] >> 4) != 4 or ip[9] != 6:
            continue
        tcp = ip[(ip[0] & 0xF) * 4:]
        if len(tcp) < 14:
            continue
        if tcp[13] & 0x02 and not tcp[13] & 0x10:      # SYN without ACK: an outbound open
            dst = ".".join(str(b) for b in ip[16:20])
            syns[f"{dst}:{struct.unpack('!H', tcp[2:4])[0]}"] += 1
    return {"pcap": str(path), "linktype": linktype, "packets": packets,
            "outbound_syns": sum(syns.values()), "by_destination": dict(syns.most_common()),
            "command": "make backstop"}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def run_view(run_dir: Path, by_destination: dict[str, int]) -> dict:
    """What the proxy and the driver recorded in the same run, beside the SYN counts."""
    calls = _read_jsonl(run_dir / "calls.jsonl")
    flows = _read_jsonl(run_dir / "flows.jsonl")
    seen = {row.get("dest_ip", "") for row in flows if row.get("dest_ip")}
    unobserved = {dest: n for dest, n in by_destination.items()
                  if not dest.startswith("127.") and dest.rsplit(":", 1)[0] not in seen}
    servers: dict[str, dict[str, int]] = {}
    for call in calls:
        row = servers.setdefault(call.get("server_id", ""), {
            "calls": 0, "completed": 0, "proxy_flows": 0, "proxy_flows_during_calls": 0})
        row["calls"] += 1
        row["completed"] += 1 if call.get("ok") else 0
    for flow in flows:
        row = servers.get(flow.get("server_id", ""))
        if row is None:
            continue
        row["proxy_flows"] += 1
        row["proxy_flows_during_calls"] += 1 if flow.get("phase") == "driving" else 0
    return {"unobserved_destinations": unobserved, "servers": servers}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    # Same resolution rule as the CLI: a bare name is a run under runs/, a path is a path. The
    # two commands take the same RUN= from the Makefile and disagreeing about what it means is a
    # difference nobody expects to have to know about.
    candidates = [Path(args.run) / "backstop.pcap",
                  Path("runs") / args.run / "backstop.pcap"]
    pcap = next((p for p in candidates if p.is_file()), None)
    if pcap is None:
        raise SystemExit(f"no backstop.pcap in {' or '.join(str(c.parent) for c in candidates)}: "
                         f"the run was driven without the pcap backstop")
    out = syn_counts(pcap)
    out.update(run_view(pcap.parent, out["by_destination"]))
    # A destination is an IP, never a hostname: gate rule 3 governs aggregate output, and this is
    # a diagnostic, but resolving here would put a hostname in something easy to paste anyway.
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
