"""A minimal MCP stdio server for testing the driver. Not part of the package.

Implements just enough of the protocol: initialize, notifications/initialized (ignored),
tools/list, tools/call (echoes). It makes no network calls; it exists only to prove the driver
speaks the protocol correctly.
"""

import json
import sys


def main() -> None:
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

        if method == "initialize":
            result = {"protocolVersion": msg["params"]["protocolVersion"],
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "mock", "version": "0"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "search", "description": "mock",
                                 "inputSchema": {"type": "object"}}]}
        elif method == "tools/call":
            params = msg.get("params", {})
            result = {"content": [{"type": "text", "text": f"called {params.get('name')}"}],
                      "isError": False}
        else:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid,
                                         "error": {"code": -32601, "message": "method not found"}}) + "\n")
            sys.stdout.flush()
            continue

        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
