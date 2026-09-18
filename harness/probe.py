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

A probe that hangs is a probe that lies by omission, so every read is bounded (see
mcpfanout.driver) and a server that starts and says nothing is written out as a timed-out
probe, with its stderr tail, rather than stopping the sweep.

Usage:
    python harness/probe.py --id everything -- npx -y @modelcontextprotocol/server-everything
"""

from __future__ import annotations

import argparse
import json
import sys

from mcpfanout.driver import StdioMCPClient

# Newest first among the HANDSHAKE revisions. The first that completes the handshake wins.
# 2026-07-28 is deliberately absent even though it is the current revision: it removed
# initialize (SEP-2575), so a handshake can never legitimately negotiate it, and a lenient
# server that echoed it back would write a protocol it does not implement into the registry.
# Probing it needs server/discover, which is a driver rewrite (see mcpfanout.driver, claim 1).
CANDIDATE_PROTOCOLS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

# npx and uvx download the package inside our subprocess, so the first response may be a cold
# minute away. Generous on initialize, tight afterwards: a server that handshakes and then hangs
# on tools/list is a finding we want in seconds, not in minutes.
STARTUP_TIMEOUT_S = 120.0
LIST_TIMEOUT_S = 30.0


def probe(command: list[str], env: dict | None = None, *,
          startup_timeout: float = STARTUP_TIMEOUT_S,
          list_timeout: float = LIST_TIMEOUT_S) -> dict:
    # Timeouts are arguments, not constants read at the call site: the test for a hung server has
    # to reproduce the hang, and at the shipped 120s startup budget times four candidates that
    # single test would cost eight minutes and get deleted by whoever next runs `make verify`.
    attempts = []
    for version in CANDIDATE_PROTOCOLS:
        try:
            with StdioMCPClient(command, env, read_timeout=list_timeout) as client:
                result = client.request("initialize", {
                    "protocolVersion": version,
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-fanout-probe", "version": "0.1.0"},
                }, timeout=startup_timeout)
                client.notify("notifications/initialized")
                tools = client.request("tools/list").get("tools", [])
                return {
                    "ok": True,
                    # The rejections on the way down are reported on success too: "accepted our
                    # first choice" and "accepted only after refusing three" are different facts
                    # about a server, and dropping them on success loses the second one.
                    "attempts": attempts,
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
            # Every rejection is kept, not just the last one: "rejected 2025-11-25 and then timed
            # out on 2024-11-05" and "timed out on all four" are different facts about a server.
            attempts.append({"protocol_version_tried": version,
                             "error": f"{type(exc).__name__}: {exc}"})
            continue
    return {"ok": False, "error": attempts[-1]["error"] if attempts else "",
            "attempts": attempts, "tools": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="server id, for the report")
    ap.add_argument("--env", default="{}", help="JSON dict of extra env vars")
    ap.add_argument("command", nargs=argparse.REMAINDER, help="-- launch command")
    args = ap.parse_args()

    command = [c for c in args.command if c != "--"]
    if not command:
        ap.error("no launch command given (use -- before it)")

    env = json.loads(args.env)
    out = probe(command, env)
    out["id"] = args.id
    out["command"] = command
    out["tool_count"] = len(out["tools"])
    # Which env keys we supplied, so a reader can tell "started with nothing" from "started only
    # because we handed it a placeholder". Keys, never values: the registry records that a
    # variable was set, not what it was set to, and a probe file is committed.
    out["env_keys_supplied"] = sorted(env)
    out["started_without_credentials"] = out["ok"] and not env
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
