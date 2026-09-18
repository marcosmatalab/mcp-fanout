"""Drive every server in the registry through the proxy, sequentially, writing the run.

Run inside the harness container by run.sh, after mitmdump is up. Sequential by design: one
call at a time per server gives the capture addon ground-truth attribution (see driver.py),
which is what lets number 5 measure how often content matching ALONE would have sufficed.

Needs the 'capture' extra (PyYAML). Never computes a number; it only produces calls.jsonl and
manifest.json. Flows are written by the addon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml  # from the 'capture' extra

from mcpfanout.driver import CallSpec, StdioMCPClient, drive
from mcpfanout.record import ToolCall, RunManifest, write_jsonl, write_manifest
from mcpfanout.redact import DEFAULT_SALT, Redactor


def load_corpus(path: Path) -> list[CallSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CallSpec(tool_name=c["tool"], arguments=c.get("arguments", {})) for c in data]


def warm(selected: list[dict]) -> int:
    """Launch each server once, handshake, and exit, to populate the npx/uv package caches.

    Why this has to happen BEFORE mitmdump starts. `npx -y pkg@ver` and `uvx pkg@ver` download
    the package inside the server subprocess, which inherits HTTP(S)_PROXY, so on a cold cache
    the installer's traffic is captured and counted as the server's fan-out. Measured, not
    theorised: the first successful smoke run of `fetch` produced 129 flows, every one of them
    uvx fetching from pypi.org and files.pythonhosted.org, and none from the tool call itself.
    That is the package manager's behavior attributed to the server under test, and it
    contaminates numbers 1, 2, 4 and 6.

    The residual, stated rather than hidden: this warm launch is NOT observed, so a server that
    egresses on first start does it here, off camera. Installing at image build time has the
    same hole. The alternative -- capture the install and label it -- was rejected because it
    puts hundreds of registry flows in the same file as a handful of tool-call flows, where any
    per-call number is swamped by them. See docs/THREATS.md threat 10.
    """
    for srv in selected:
        sid = srv["id"]
        try:
            with StdioMCPClient(list(srv["launch"]), read_timeout=60.0) as client:
                client.initialize(timeout=300.0)
                n = len(client.list_tools())
            print(f"[warm] {sid}: cache populated, {n} tools")
        except Exception as exc:  # a server that cannot start is reported, not fatal: the
            # capture pass records it as zero egress, which is the finding.
            print(f"[warm] {sid}: did not start ({type(exc).__name__}: {exc})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--proxy", default="http://127.0.0.1:8080")
    ap.add_argument("--salt", default="")
    ap.add_argument("--only", action="append", default=[], metavar="ID",
                    help="drive only these server ids (repeatable). Default: all of them.")
    ap.add_argument("--warm", action="store_true",
                    help="only populate package caches and exit; run this BEFORE the proxy starts")
    args = ap.parse_args()

    reg = yaml.safe_load(Path(args.registry).read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir)
    control_dir = run_dir / "control"
    k, w = int(reg.get("k", 16)), int(reg.get("w", 8))
    salt = args.salt.encode() or DEFAULT_SALT
    redactor = Redactor(salt=salt, k=k, w=w)
    run_id = run_dir.name

    # Every server process inherits the proxy so its HTTP(S) egress passes through mitmdump.
    proxy_env = {"HTTP_PROXY": args.proxy, "HTTPS_PROXY": args.proxy,
                 "http_proxy": args.proxy, "https_proxy": args.proxy}

    all_calls: list[ToolCall] = []
    server_ids: list[str] = []
    corpus_hash = hashlib.sha256()

    selected = reg.get("servers", [])
    if args.only:
        # Selecting a subset is for a smoke test, so an unknown id must be an error rather than
        # a silent empty run: "typo in the id" and "server produced nothing" look identical in
        # the output otherwise, and one of those is a finding.
        known = {s["id"] for s in selected}
        unknown = sorted(set(args.only) - known)
        if unknown:
            raise SystemExit(f"[drive_all] unknown server id(s): {unknown}. Known: {sorted(known)}")
        selected = [s for s in selected if s["id"] in set(args.only)]
        print(f"[drive_all] SUBSET: driving {[s['id'] for s in selected]} only. "
              f"A run driven with --only is not a measurement of the registry.")

    if args.warm:
        return warm(selected)

    for srv in selected:
        sid = srv["id"]
        server_ids.append(sid)
        corpus = load_corpus(Path(srv["corpus_ref"]))
        corpus_hash.update(Path(srv["corpus_ref"]).read_bytes())
        results = drive(
            command=list(srv["launch"]), corpus=corpus, run_id=run_id, server_id=sid,
            env=proxy_env, redactor=redactor, control_dir=control_dir,
        )
        for r in results:
            # Every field of DriveResult that ToolCall has, or the record lies by default value:
            # this path dropped ok/error/stdout_noise_lines and the run reported "ok: true,
            # stdout_noise_lines: 0" for calls the driver had just counted 7 noise lines on.
            all_calls.append(ToolCall(run_id, sid, r.call_id, r.tool_name, r.args_present,
                                      r.traceparent, ok=r.ok, error=r.error,
                                      stdout_noise_lines=r.stdout_noise_lines))
        # A server that fails to launch is a data point (zero egress), not a stop; log to stderr.
        failed = [r for r in results if not r.ok]
        if failed:
            # The reason, not just the count. "2 calls errored" sent me diffing packet logs for
            # an hour over what turned out to be one line of npm output on the server's stdout.
            print(f"[drive_all] {sid}: {len(failed)} calls errored (recorded, continuing)")
            for r in failed:
                print(f"[drive_all]   {r.call_id} {r.tool_name}: {r.error[:200]}")
        noise = sum(r.stdout_noise_lines for r in results)
        if noise:
            print(f"[drive_all] {sid}: {noise} non-JSON-RPC lines on stdout "
                  f"(the server is corrupting its own protocol channel; recorded per call)")

    write_jsonl(run_dir / "calls.jsonl", all_calls)
    write_manifest(run_dir / "manifest.json", RunManifest(
        run_id=run_id, created=datetime.now(timezone.utc).isoformat(),
        salt_fixed=(salt == DEFAULT_SALT), k=k, w=w,
        corpus_sha256=corpus_hash.hexdigest(), server_ids=server_ids,
        # Taken from the registry, where it was MEASURED by harness/probe.py, rather than
        # re-derived here: two places computing the same fact is how they diverge.
        server_protocol_versions={s["id"]: s.get("protocol_version_answered", "")
                                  for s in selected
                                  if s.get("protocol_version_answered")},
        tool_versions={"note": "fill with pinned server digests before publishing"},
        notes=("Capture run. See docs/THE-GATE.md before publishing any number."
               + (f" SUBSET RUN: --only {sorted(set(args.only))}; the registry holds "
                  f"{len(reg.get('servers', []))} servers. Not a measurement of the registry."
                  if args.only else "")),
    ))
    print(f"[drive_all] wrote {len(all_calls)} calls across {len(server_ids)} servers to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
