"""Drive the phase A bench: concurrent waves against our own server and our own sink.

This file is the HARNESS SIDE of the bench and may use mcpfanout, unlike bench/server.py and
bench/sink.py which must stand alone (tests/test_bench_isolation.py). The split matters: the
pattern generator and the instrument have to be unable to share a mechanism, or the precision
figure measures the sensor against a copy of itself.

What it does, in order: expand bench/waves.json into waves, then for each wave publish the whole
in-flight set, send every call at once, collect every response. The wave is the unit because
CONTENT_UNIQUE requires more than one call in flight, and the window count the addon records is
what separates it from CONTENT_MATCH_UNCONTESTED.

It writes bench_calls.jsonl next to the run: the harness's record of what it drove, which the
comparator reads alongside the bench's own truth ledger and the captured flows. Three files, three
authors, which is the arrangement that makes the comparison mean something.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from mcpfanout.driver import CallSpec, StdioMCPClient, drive_wave
from mcpfanout.record import PASS_BENCH, RunManifest, ToolCall, write_jsonl, write_manifest
from mcpfanout.redact import DEFAULT_SALT, Redactor

# 40 bytes of synthetic material per fragment, well over k = 16 so a literal run is detectable
# and not coincidental. Never a real secret (docs/DOCTRINE.md).
#
# NO TWO FRAGMENTS MAY SHARE A 16-BYTE RUN, and this is a correctness requirement of the
# experiment, not tidiness. The first version was "BENCHFRAG_<tag>_0123456789abcdef0123456":
# readable, and wrong. Every fragment shared the 10-byte prefix AND a 24-byte constant tail, so
# k-grams from the tail appeared in every call's argument digests, every flow matched every call,
# and the all_distinct cell reported matching_calls_in_window = N. The bench said CONTENT_AMBIGUOUS
# where the answer was CONTENT_UNIQUE, and the sensor was right each time. A bench whose fragments
# collide cannot measure discrimination: it measures its own collisions.
#
# So the body is a keyed digest of the tag, which makes a shared 16-byte run a hash collision
# rather than a design property. The 2-byte "BF" prefix keeps the material greppable and is far
# too short to be a shared run.
FRAGMENT_PREFIX = "BF"
FRAGMENT_BODY_HEX = 38


def _fragment(tag: str) -> str:
    import hashlib
    body = hashlib.blake2b(tag.encode(), key=b"mcp-fanout/bench/fragments/v1",
                           digest_size=32).hexdigest()
    return FRAGMENT_PREFIX + body[:FRAGMENT_BODY_HEX]


def _wave_specs(cell: dict, n: int, wave_id: str, first_slot: int) -> list[CallSpec]:
    """Expand one cell at one concurrency level into N concurrent CallSpecs.

    fragment_mode is the experiment's independent variable:
      distinct     every call gets its own fragment      -> content can discriminate
      shared       every call gets the SAME fragment     -> content cannot discriminate
      pair_shared  calls 0 and 1 share, the rest unique  -> both answers in one wave
      none         no fragment and no arguments at all   -> nothing can travel
    """
    tpl = cell["template"]
    mode = tpl["fragment_mode"]
    specs: list[CallSpec] = []
    for i in range(n):
        if mode == "none":
            frag = ""
        elif mode == "shared":
            frag = _fragment(f"{wave_id}shared")
        elif mode == "pair_shared":
            frag = _fragment(f"{wave_id}pair") if i < 2 else _fragment(f"{wave_id}u{i}")
        else:
            frag = _fragment(f"{wave_id}u{i}")

        # A GLOBAL slot per call, not a position within the wave: each call therefore has its
        # own destination host for the whole run, which is what lets the comparator join one
        # truth-ledger row to one observed flow without ambiguity.
        args: dict = {"slot": first_slot + i}
        if tpl["tool"] == "bench_emit_encoded":
            args["encoding"] = tpl["encoding"]
        else:
            args["channel"] = tpl["channel"]
        if frag:
            args["fragment"] = frag
        if "count" in tpl:
            args["count"] = tpl["count"]
        if "delay_ms" in tpl:
            args["delay_ms"] = tpl["delay_ms"]
        specs.append(CallSpec(tool_name=tpl["tool"], arguments=args))
    return specs


def _plan(waves_path: Path) -> list[tuple[dict, int, str]]:
    plan = json.loads(waves_path.read_text(encoding="utf-8"))
    out = []
    for group in ("discrimination_cells", "channel_cells", "sensor_cells"):
        for cell in plan[group]:
            for n in cell["n"]:
                out.append(({**cell, "group": group}, n, f"{cell['cell'][:6]}{n}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--waves", default="bench/waves.json")
    ap.add_argument("--server", default="bench/server.py")
    ap.add_argument("--truth", required=True, help="path the BENCH writes its own ledger to")
    ap.add_argument("--proxy", default="http://127.0.0.1:8080")
    ap.add_argument("--salt", default="")
    ap.add_argument("--sink-port", default="8099")
    ap.add_argument("--settle-seconds", type=float, default=3.0,
                    help="wait after the last wave so late egress still lands in the capture")
    args = ap.parse_args()

    import sys
    import time

    run_dir = Path(args.run_dir)
    control_dir = run_dir / "control"
    salt = args.salt.encode() or DEFAULT_SALT
    redactor = Redactor(salt=salt)
    run_id = run_dir.name
    server_id = "bench"

    # The bench server inherits the proxy, so its egress passes through mitmdump, and it is told
    # where to write its own ledger. It is NOT told anything about the harness control directory:
    # that is the isolation the precision figure depends on.
    env = {"HTTP_PROXY": args.proxy, "HTTPS_PROXY": args.proxy,
           "http_proxy": args.proxy, "https_proxy": args.proxy,
           "BENCH_TRUTH": args.truth, "BENCH_SINK_PORT": args.sink_port}

    plan = _plan(Path(args.waves))
    all_calls: list[ToolCall] = []
    # The harness's declaration of WHAT IT DROVE: which call used which destination slot, in
    # which cell, and what grade that cell expects. The comparator needs it to know which cell a
    # flow belongs to; it is intent, not observation, and it is kept apart from both the bench's
    # ledger and the sensor's flows. Three files, three authors.
    plan_rows: list[dict] = []
    index = 0

    with StdioMCPClient([sys.executable, args.server, "--truth", args.truth], env,
                        read_timeout=60.0) as client:
        client.initialize(timeout=60.0)
        client.list_tools()
        for cell, n, wave_id in plan:
            specs = _wave_specs(cell, n, wave_id, first_slot=index)
            results = drive_wave(client, specs, run_id=run_id, server_id=server_id,
                                 redactor=redactor, control_dir=control_dir,
                                 start_index=index, timeout=60.0)
            for spec, r in zip(specs, results):
                all_calls.append(ToolCall(run_id, server_id, r.call_id, r.tool_name,
                                          r.args_present, r.traceparent, ok=r.ok, error=r.error,
                                          stdout_noise_lines=r.stdout_noise_lines, wave_size=n))
                plan_rows.append({
                    "call_id": r.call_id, "cell": cell["cell"], "group": cell["group"],
                    "n": n, "slot": spec.arguments["slot"], "tool": spec.tool_name,
                    "channel": spec.arguments.get("channel",
                                                  "body:" + spec.arguments.get("encoding", "")),
                    "expect": cell.get("expect", ""),
                    "fragment_present": bool(spec.arguments.get("fragment")),
                })
            failed = [r for r in results if not r.ok]
            print(f"[bench] {cell['cell']} n={n}: {len(results)} calls"
                  + (f", {len(failed)} errored" if failed else ""))
            for r in failed:
                print(f"[bench]   {r.call_id}: {r.error[:160]}")
            index += n

        # Late egress arrives after its wave, by design. Waiting here lets the capture see it
        # while the in-flight set is already empty, which is the point: it must come out
        # unattributed rather than pinned to whatever ran last.
        if args.settle_seconds:
            print(f"[bench] settling {args.settle_seconds}s for late egress")
            time.sleep(args.settle_seconds)

    write_jsonl(run_dir / "bench_calls.jsonl", all_calls)
    (run_dir / "bench_plan.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in plan_rows), encoding="utf-8")
    write_manifest(run_dir / "manifest.json", RunManifest(
        run_id=run_id, created=datetime.now(timezone.utc).isoformat(),
        salt_fixed=(salt == DEFAULT_SALT), k=redactor.k, w=redactor.w,
        corpus_sha256=hashlib.sha256(Path(args.waves).read_bytes()).hexdigest(),
        server_ids=[server_id], tool_versions={"bench": "phase-a"},
        pass_name=PASS_BENCH,
        server_protocol_versions={server_id: "2025-11-25"},
        notes=("PHASE A BENCH run, not a measurement of any third-party server. Ground truth is "
               "the bench's own ledger; see docs/PROTOCOL.md and mcpfanout.bench_metrics."),
    ))
    # calls.jsonl is what the aggregate reads, so the bench's calls are written there too.
    write_jsonl(run_dir / "calls.jsonl", all_calls)
    print(f"[bench] drove {len(all_calls)} calls in {len(plan)} waves into {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
