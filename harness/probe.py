"""Probe one MCP server: launch it, handshake, and dump its real tools.

Why this exists: registry/servers.yaml must carry the tools a server ACTUALLY exposes, not the
ones we guessed. A corpus entry naming a non-existent tool produces an error call, which records
zero egress and silently biases numbers 1, 2 and 5 downward (docs/THREATS.md, threat 1). This is
the tool that closes that gap, and it is part of the gate workflow, not a scratch script.

It never calls a tool. It does initialize plus tools/list and exits, so it is safe to run against
a server with no credentials and it cannot cause egress beyond whatever the server does on start.

Protocol version negotiation: we try our preferred revision first and fall back through older
ones, because a server pinned to an older spec rejects an unknown protocolVersion outright. The
version that succeeded is reported, which is itself useful registry data.

Usage:
    python harness/probe.py --id everything -- npx -y @modelcontextprotocol/server-everything
"""

from __future__ import annotations

import argparse
import json
import sys

from mcpfanout.driver import StdioMCPClient

# Newest first. The first that completes the handshake wins.
CANDIDATE_PROTOCOLS = ["2026-07-28", "2025-06-18", "2025-03-26", "2024-11-05"]


def probe(command: list[str], env: dict | None = None) -> dict:
    last_error = ""
    for version in CANDIDATE_PROTOCOLS:
        try:
            with StdioMCPClient(command, env) as client:
                result = client.request("initialize", {
                    "protocolVersion": version,
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-fanout-probe", "version": "0.1.0"},
                })
                client.notify("notifications/initialized")
                tools = client.request("tools/list").get("tools", [])
                return {
                    "ok": True,
                    "protocol_version_used": version,
                    "server_protocol_version": result.get("protocolVersion", ""),
                    "server_info": result.get("serverInfo", {}),
                    "capabilities": result.get("capabilities", {}),
                    "tools": [
                        {
                            "name": t.get("name", ""),
                            "description": (t.get("description") or "")[:300],
                            "inputSchema": t.get("inputSchema", {}),
                        }
                        for t in tools
                    ],
                }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
    return {"ok": False, "error": last_error, "tools": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="server id, for the report")
    ap.add_argument("--env", default="{}", help="JSON dict of extra env vars")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- launch command")
    args = ap.parse_args()

    command = [c for c in args.command if c != "--"]
    if not command:
        ap.error("no launch command given (use -- before it)")

    out = probe(command, json.loads(args.env))
    out["id"] = args.id
    out["command"] = command
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
