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

from mcpfanout.driver import CallSpec, drive
from mcpfanout.record import ToolCall, RunManifest, write_jsonl, write_manifest
from mcpfanout.redact import DEFAULT_SALT, Redactor


def load_corpus(path: Path) -> list[CallSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CallSpec(tool_name=c["tool"], arguments=c.get("arguments", {})) for c in data]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--proxy", default="http://127.0.0.1:8080")
    ap.add_argument("--salt", default="")
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

    for srv in reg.get("servers", []):
        sid = srv["id"]
        server_ids.append(sid)
        corpus = load_corpus(Path(srv["corpus_ref"]))
        corpus_hash.update(Path(srv["corpus_ref"]).read_bytes())
        results = drive(
            command=list(srv["launch"]), corpus=corpus, run_id=run_id, server_id=sid,
            env=proxy_env, redactor=redactor, control_dir=control_dir,
        )
        for r in results:
            all_calls.append(ToolCall(run_id, sid, r.call_id, r.tool_name, r.args_present, r.traceparent))
        # A server that fails to launch is a data point (zero egress), not a stop; log to stderr.
        failed = [r for r in results if not r.ok]
        if failed:
            print(f"[drive_all] {sid}: {len(failed)} calls errored (recorded, continuing)")

    write_jsonl(run_dir / "calls.jsonl", all_calls)
    write_manifest(run_dir / "manifest.json", RunManifest(
        run_id=run_id, created=datetime.now(timezone.utc).isoformat(),
        salt_fixed=(salt == DEFAULT_SALT), k=k, w=w,
        corpus_sha256=corpus_hash.hexdigest(), server_ids=server_ids,
        tool_versions={"note": "fill with pinned server digests before publishing"},
        notes="Capture run. See docs/THE-GATE.md before publishing any number.",
    ))
    print(f"[drive_all] wrote {len(all_calls)} calls across {len(server_ids)} servers to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
