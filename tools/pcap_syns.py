"""Count outbound TCP SYNs per destination in a run's backstop pcap. Standard library only.

WHY THIS EXISTS. The proxy sees only clients that honour HTTP(S)_PROXY. Node's global fetch
(undici) does not, so a server using it reaches its API while `flows.jsonl` stays empty for it and
the tool call plainly succeeds (docs/THREATS.md threat 6). The pcap is the only evidence that the
traffic happened at all, and until this file existed the claim rested on an ad-hoc script nobody
could re-run. Rule 6: a number that appears in a threat needs a command behind it.

What it is NOT: reconciliation. It counts connections, it cannot say what was in them, and a SYN
count is not comparable with a flow count (one flow is a request, one SYN is a connection that may
carry many or none). It answers exactly one question: did bytes leave for that host at all.

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
L2_LEN = {1: 14, 101: 4, 113: 16, 276: 20}   # EN10MB, RAW, LINUX_SLL, LINUX_SLL2


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    pcap = Path(args.run) / "backstop.pcap"
    if not pcap.is_file():
        raise SystemExit(f"{pcap} not found: the run was driven without the pcap backstop")
    out = syn_counts(pcap)
    # A destination is an IP, never a hostname: gate rule 3 governs aggregate output, and this is
    # a diagnostic, but resolving here would put a hostname in something easy to paste anyway.
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
