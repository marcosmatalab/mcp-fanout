"""The bench's own HTTP sink: a destination we control, so egress to it is ground truth.

Standard library only, and no import from mcpfanout anywhere in bench/. See
tests/test_bench_isolation.py for why that is a measured property and not a preference.

It answers 204 to everything and keeps nothing. It exists so the bench server has somewhere real
to send bytes: "known egress to destinations we own" is what makes capture recall computable,
because only then is there a denominator of transfers we caused on purpose.

Plain HTTP, not HTTPS, and the cost is stated rather than hidden. The bench measures ATTRIBUTION
and RECALL through the proxy, and both are observable on an HTTP request line and body. What the
bench therefore does NOT cover is a TLS-specific capture defect: a failure that only appears when
mitmproxy terminates a real handshake would pass the sensor gate here and show up in phase B. The
alternative, serving TLS from the sink with a cert mitmproxy would then have to distrust upstream,
buys a narrower gap than it costs in moving parts. Recorded in docs/PROTOCOL.md as a bench limit.

One listening port serves every sink hostname. The hostnames (sink00.bench.invalid and up, mapped
to loopback in the image) exist to give each concurrent call a DISTINCT destination, which is the
join key the comparator needs; the sink itself does not care which name it was reached by.
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
import sys


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _drain_and_ack(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        if length:
            self.rfile.read(length)
        self.send_response(204)
        self.send_header("content-length", "0")
        self.end_headers()

    do_GET = do_POST = do_PUT = _drain_and_ack

    def log_message(self, *args) -> None:
        # Silence. The sink is a destination, not an observer: if it logged what it received it
        # would become a second source of truth about the payload, and the bench has one.
        return


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()
    srv = _Server((args.host, args.port), _Handler)
    print(f"[sink] listening on {args.host}:{args.port}", file=sys.stderr, flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
