"""Command line entry point.

Subcommands:
  aggregate  Compute the six numbers from a run (the rule-6 commands behind the Makefile).
  selftest   Build a synthetic run and compute its numbers, with no Docker and no network.
  run        Drive the pinned servers under capture and write a real run (delegates to harness/).

Aggregate and selftest are pure standard library. `run` needs the 'capture' extra and Docker;
it is intentionally a thin delegator so the heavy, environment-specific orchestration lives in
harness/run.sh where it can be read and audited as a shell pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .aggregate import Run, compute_all, number_1, number_2, number_3, number_4, number_5, number_6
from .classify import Registry


def _resolve_run(run_arg: str, runs_root: Path = Path("runs")) -> Path:
    """Turn 'latest' or a path into a concrete run directory."""
    if run_arg != "latest":
        p = Path(run_arg)
        if not (p / "manifest.json").exists():
            sys.exit(f"error: {p} is not a run directory (no manifest.json)")
        return p
    if not runs_root.exists():
        sys.exit("error: no runs/ directory yet. Run `make selftest` or `make run` first.")
    candidates = [d for d in runs_root.iterdir() if (d / "manifest.json").exists()]
    if not candidates:
        sys.exit("error: runs/ has no completed run yet.")
    # Newest by modification time. Deterministic given the filesystem; ties are vanishingly rare
    # and never affect a published number (a number is tied to a specific run directory).
    return max(candidates, key=lambda d: d.stat().st_mtime)


def _load_registry() -> Registry:
    """Load registry/selfhostable.json if present, else the embedded defaults."""
    path = Path("registry/selfhostable.json")
    if path.exists():
        return Registry.from_dict(json.loads(path.read_text(encoding="utf-8")))
    return Registry()


def _cmd_aggregate(args: argparse.Namespace) -> int:
    run = Run.load(_resolve_run(args.run))
    registry = _load_registry()
    single = {
        "1": lambda: number_1(run), "2": lambda: number_2(run), "3": lambda: number_3(run),
        "4": lambda: number_4(run), "5": lambda: number_5(run), "6": lambda: number_6(run, registry),
    }
    if args.number == "all":
        out = compute_all(run, registry)
    else:
        out = single[args.number]()
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def _cmd_selftest(args: argparse.Namespace) -> int:
    from .demo import build_demo_run
    out_dir = Path(args.out)
    build_demo_run(out_dir)
    run = Run.load(out_dir)
    print(json.dumps(compute_all(run, _load_registry()), indent=2, sort_keys=True))
    return 0


def _cmd_prep_context(args: argparse.Namespace) -> int:
    """Pre-digest the session context files into a content-free index for the capture addon.

    Output is {reference_id: [salted_digest, ...]}. The raw context bytes are read here and not
    written anywhere: only digests leave this process, which is the digest-only guarantee applied
    before capture even starts.
    """
    from .redact import DEFAULT_SALT, Redactor
    salt = os.environ.get("MCPFANOUT_SALT", "").encode() or DEFAULT_SALT
    redactor = Redactor(salt=salt)
    ctx_dir = Path(args.context_dir)
    index: dict[str, list[str]] = {}
    for path in sorted(ctx_dir.rglob("*")):
        if path.is_file():
            ref = str(path.relative_to(ctx_dir.parent))
            index[ref] = sorted(redactor.kgram_digest_set(path.read_bytes()))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index), encoding="utf-8")
    print(f"wrote {out} with {len(index)} references")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    script = Path(__file__).resolve().parents[2] / "harness" / "run.sh"
    if not script.exists():
        sys.exit("error: harness/run.sh not found.")
    # Delegate to the shell harness INSIDE the container, via compose. This used to call
    # `bash harness/run.sh` directly, which ran the container-only script on the host: run.sh
    # installs a CA into the system trust store, so `make run` on a host would have modified the
    # operator's own machine, against gate rule 5. Compose is the boundary that makes the rule
    # true instead of merely documented. Any failure (no Docker, build error, missing extra)
    # surfaces as compose's own exit code and message, which is more honest than a Python
    # wrapper pretending to know why the container failed.
    compose = Path(__file__).resolve().parents[2] / "harness" / "docker-compose.yml"
    if not compose.exists():
        sys.exit("error: harness/docker-compose.yml not found.")
    cmd = ["docker", "compose", "-f", str(compose), "run", "--rm", "--build", "harness",
           "--registry", args.registry, "--out", args.out]
    for sid in args.only:
        cmd += ["--only", sid]
    return subprocess.call(cmd)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mcp-fanout", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("aggregate", help="compute the six numbers from a run")
    a.add_argument("--run", default="latest", help="'latest' or a path to runs/<id>")
    a.add_argument("--number", default="all", choices=["1", "2", "3", "4", "5", "6", "all"])
    a.set_defaults(func=_cmd_aggregate)

    s = sub.add_parser("selftest", help="build a synthetic run and show its numbers (no Docker)")
    s.add_argument("--out", default="runs/selftest", help="output run directory")
    s.set_defaults(func=_cmd_selftest)

    pc = sub.add_parser("prep-context", help="pre-digest context files for the capture addon")
    pc.add_argument("--context-dir", default="corpus/context")
    pc.add_argument("--out", default="runs/live/context.json")
    pc.set_defaults(func=_cmd_prep_context)

    r = sub.add_parser("run", help="drive the pinned servers under capture (needs Docker)")
    r.add_argument("--registry", default="registry/servers.yaml")
    r.add_argument("--out", default="runs/")
    r.add_argument("--only", action="append", default=[], metavar="ID",
                   help="drive only these server ids (repeatable), for a smoke test")
    r.set_defaults(func=_cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
