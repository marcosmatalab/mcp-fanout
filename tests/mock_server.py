"""A minimal MCP stdio server for testing the driver. Not part of the package.

Implements just enough of the protocol: initialize, notifications/initialized (ignored),
tools/list, tools/call (echoes). It makes no network calls; it exists only to prove the driver
speaks the protocol correctly.

It NEGOTIATES rather than mirrors. The earlier version echoed back whatever protocolVersion the
client sent, which meant no test could ever catch the driver announcing a revision the server
does not implement -- and that is exactly the defect that shipped (driver.PROTOCOL_VERSION said
2026-07-28, a revision with no initialize at all). A mock that agrees with everything tests
nothing. Two knobs, both env vars, so one file covers every case:

  MOCK_SUPPORTED_PROTOCOLS   comma-separated; anything else is rejected. Default: 2025-11-25.
  MOCK_HANG                  "1" to accept the request and never answer, for timeout tests.
  MOCK_STDOUT_NOISE          "1" to emit npm-style junk on stdout before each reply, the way
                             mcp-server-fetch 2026.8.18 does when it shells out to npm.
"""

import json
import os
import sys
import time

DEFAULT_SUPPORTED = "2025-11-25"
TOOL_NAMES = {"search"}


def supported() -> list[str]:
    return [v.strip() for v in
            os.environ.get("MOCK_SUPPORTED_PROTOCOLS", DEFAULT_SUPPORTED).split(",") if v.strip()]


def main() -> None:
    if os.environ.get("MOCK_HANG") == "1":
        # Start, stay alive, answer nothing. This is the shape of the failure that used to hang
        # the harness forever, so it has to be reproducible in a test.
        while True:
            time.sleep(3600)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        mid = msg.get("id")

        if mid is None:
            # A notification (e.g. notifications/initialized). Nothing to answer.
            continue

        error = None
        result = None
        if method == "initialize":
            asked = msg["params"]["protocolVersion"]
            if asked in supported():
                # Answer with OUR version, which is what a real server does: the client asked,
                # the server decides. Echoing the client's string back is the bug this replaces.
                result = {"protocolVersion": supported()[0],
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "mock", "version": "0"}}
            else:
                # -32602 (Invalid params), not -32022 (UnsupportedProtocolVersion): that code was
                # only allocated in 2026-07-28, and this mock speaks the handshake revisions.
                error = {"code": -32602, "message": f"unsupported protocolVersion {asked}",
                         "data": {"supported": supported()}}
        elif method == "tools/list":
            result = {"tools": [{"name": n, "description": "mock",
                                 "inputSchema": {"type": "object"}} for n in sorted(TOOL_NAMES)]}
        elif method == "tools/call":
            params = msg.get("params", {})
            name = params.get("name")
            if name not in TOOL_NAMES:
                # A real server rejects a tool it does not have. The mock used to answer any
                # name at all, which meant no driver test could tell a real call from a call to
                # a tool that does not exist -- the exact defect the corpus had.
                error = {"code": -32602, "message": f"Unknown tool: {name}",
                         "data": {"available": sorted(TOOL_NAMES)}}
            else:
                result = {"content": [{"type": "text", "text": f"called {name}"}],
                          "isError": False}
        else:
            error = {"code": -32601, "message": "method not found"}

        if os.environ.get("MOCK_STDOUT_NOISE") == "1":
            # Verbatim shape of what mcp-server-fetch 2026.8.18 puts on its JSON-RPC channel:
            # a bare newline, then npm's summary. Both must be skipped, and both counted.
            sys.stdout.write("\n")
            sys.stdout.write("added 41 packages, and audited 42 packages in 4s\n")
            sys.stdout.flush()

        payload = {"jsonrpc": "2.0", "id": mid}
        payload["error" if error else "result"] = error if error else result
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
