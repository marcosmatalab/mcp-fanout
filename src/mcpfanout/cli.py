"""Command line entry point.

Subcommands:
  aggregate  Compute the six numbers from a run (the rule-6 commands behind the Makefile).
  figures    Write a run's normalized aggregate to docs/figures/ as a committed artifact.
  bench-verify  Phase A instrument metrics (recall, precision, false provenance).
  disclosure-check  Gate rule 7: which of a run's destinations nobody declared. Operator-only
             output: it names servers and hosts, so it is written into the run and never published.
  selftest   Build a synthetic run and compute its numbers, with no Docker and no network.
  run        Drive the pinned servers under capture and write a real run (delegates to harness/).
             --pass picks which phase B pass to drive; the two are separate runs (docs/PHASES.md).

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
from .classify import PACKAGE_INFRASTRUCTURE_PATH, ExclusionList, Registry


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
    # A declared exclusion list, loaded from registry/ and cited in the output. None is a
    # reported state, not a default: number_1 withholds the excluded figure and says why.
    exclusions = ExclusionList.load(PACKAGE_INFRASTRUCTURE_PATH)
    single = {
        "1": lambda: number_1(run, exclusions), "2": lambda: number_2(run),
        "3": lambda: number_3(run), "4": lambda: number_4(run),
        "5": lambda: number_5(run, exclusions),
        "6": lambda: number_6(run, registry),
    }
    if args.number == "all":
        out = compute_all(run, registry, exclusions)
    else:
        out = single[args.number]()
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def _cmd_selftest(args: argparse.Namespace) -> int:
    from .demo import build_demo_run
    out_dir = Path(args.out)
    build_demo_run(out_dir)
    run = Run.load(out_dir)
    print(json.dumps(compute_all(run, _load_registry(),
                                 ExclusionList.load(PACKAGE_INFRASTRUCTURE_PATH)),
                     indent=2, sort_keys=True))
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


def _cmd_bench_verify(args: argparse.Namespace) -> int:
    """Compare the phase A bench's own truth ledger against what the sensor recorded.

    Separate from `aggregate` on purpose. The six numbers describe the PHENOMENON and are
    computable for any run; these three describe the INSTRUMENT and are computable only where we
    caused every transfer and know its cause. Putting them in one command would invite quoting a
    recall figure off a phase B run, which is a number with no denominator (gate rule 8).
    """
    from .bench_metrics import compute
    out = compute(_resolve_run(args.run), args.truth)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out.get("ok") else 1


def _cmd_disclosure_check(args: argparse.Namespace) -> int:
    """Gate rule 7 as a command. Exit 0 if clear, 1 if anything needs reviewing or is unknown.

    Non-zero for "undeterminable" as well as for "review required", deliberately. The declaration
    file being absent means the rule was not evaluated, and a zero exit there would let a missing
    file read as a clean run in exactly the place where a clean reading is most expensive.

    The report is written into the RUN directory, which is gitignored, because it names servers and
    destination hosts (gate rule 3). Nothing here goes to docs/figures/.
    """
    from .disclosure import DECLARED_DESTINATIONS_PATH, DeclaredDestinations, VERDICT_CLEAR, check
    run_dir = _resolve_run(args.run)
    run = Run.load(run_dir)
    declared = DeclaredDestinations.load(args.declared or DECLARED_DESTINATIONS_PATH)
    report = check(run.flows, declared)
    report["run_id"] = run.manifest.run_id
    report["pass"] = run.manifest.pass_name or "unlabelled"
    report["command"] = f"python -m mcpfanout.cli disclosure-check --run runs/{run.manifest.run_id}"
    # Printed BEFORE it is saved, and the save is allowed to fail. The verdict is the product of
    # this command; the file is a convenience, and a run directory written by the container is
    # root-owned, so a host-side re-check would otherwise lose the report to a permission error
    # after having computed it. Measured the hard way, on exactly that.
    print(json.dumps(report, indent=2, sort_keys=True))
    out = run_dir / "disclosure.json"
    try:
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[disclosure] wrote {out}", file=sys.stderr)
    except OSError as exc:
        print(f"[disclosure] report NOT saved to {out} ({exc.strerror}); the verdict above and "
              f"the exit code still stand", file=sys.stderr)
    return 0 if report["verdict"] == VERDICT_CLEAR else 1


def _cmd_figures(args: argparse.Namespace) -> int:
    """Write a run's NORMALIZED AGGREGATE to docs/figures/ as a committed artifact.

    Why this exists. Gate rule 6 wants a command behind every published figure, and gate rule 4
    refuses to track runs, so a figure quoted in a document was measured but not re-derivable
    from the repository: a reader could only re-run the capture and get their own numbers. That
    tension is resolved by committing the AGGREGATE rather than the run. The aggregate is counts,
    ratios and category breakdowns with no hostname, no server id, no tool name and no digest, so
    rule 3 holds; the run keeps the per-flow records and the salted digests tied to specific
    servers, and stays untracked, so rule 4 holds.

    Volatile provenance (run id, wall-clock time, the command) is kept in its own block, apart
    from the numbers. Two captures of the same servers differ in those fields and must still be
    comparable on the normalized result, which is level 2 of gate rule 1.
    """
    run_dir = _resolve_run(args.run)
    run = Run.load(run_dir)
    payload = {
        "normalized": True,
        "provenance": {
            "run_id": run.manifest.run_id,
            "created": run.manifest.created,
            "salt_fixed": run.manifest.salt_fixed,
            "corpus_sha256": run.manifest.corpus_sha256,
            "server_count": len(run.manifest.server_ids),
            "notes": run.manifest.notes,
            # The command that regenerates this file, in the file, so a reader never has to
            # reconstruct it from a Makefile.
            "command": f"python -m mcpfanout.cli figures --run runs/{run.manifest.run_id}",
        },
    }
    computed = compute_all(run, _load_registry(), ExclusionList.load(PACKAGE_INFRASTRUCTURE_PATH))
    # The pass sits in provenance because it is a property of how the run was driven, and it is
    # NOT optional: a grade distribution whose driving condition is unknown cannot be read at all
    # (docs/PHASES.md, phase B: two passes, published separately and labelled by pass).
    payload["provenance"]["pass"] = computed["pass"]
    # Driving alongside the numbers, never inside them: it is the denominator (how many calls
    # errored, at which wave size), and a reader who has the six without it cannot tell a server
    # that egresses nothing from a server whose calls failed.
    payload["driving"] = computed["driving"]
    payload["numbers"] = computed["numbers"]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run.manifest.run_id}.json"
    # Sorted keys and a trailing newline: this file is committed and diffed, so two runs of the
    # command over the same run must produce identical bytes (gate rule 1, level 1).
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")

    # A phase A run carries a second, differently shaped artifact: the instrument block. It is
    # written by the same command so there is one command behind both figures (rule 2), and it is
    # a separate file because the two answer different questions and must not be quotable as one.
    if (run_dir / "bench_truth.jsonl").is_file():
        inst_out = out_dir / f"{run.manifest.run_id}-instrument.json"
        inst_out.write_text(json.dumps(_instrument_artifact(run_dir, run.manifest.run_id),
                                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {inst_out}")
    return 0


def _instrument_artifact(run_dir: Path, run_id: str) -> dict:
    """The publishable form of the phase A instrument block.

    One transformation, and it is a rule-3 requirement rather than tidiness:
    ``hosts_sent_to_but_never_observed`` is a list of DESTINATION HOSTNAMES, and no host may
    appear in published output. Committed, it becomes a count. The full list stays in the run's
    own instrument.json for the operator, which is the same division everything else uses: the
    run keeps identifying detail, the artifact keeps counts.
    """
    from .bench_metrics import compute
    inst = compute(run_dir)
    capture = dict(inst.get("capture", {}))
    missed = capture.pop("hosts_sent_to_but_never_observed", [])
    capture["hosts_sent_to_but_never_observed_count"] = len(missed)
    return {
        "normalized": True,
        "phase": "A",
        "provenance": {
            "run_id": run_id,
            "command": f"python -m mcpfanout.cli bench-verify --run runs/{run_id}",
            "what_this_is": ("the phase A bench's instrument block: capture recall, attribution "
                             "precision and false provenance matches, from comparing the bench's "
                             "own truth ledger against what the sensor recorded"),
            "ground_truth_author": ("bench/server.py, from inside its own handler. It imports "
                                    "nothing from mcpfanout and never reads the harness control "
                                    "directory; tests/test_bench_isolation.py enforces both"),
            "not_computable_elsewhere": ("recall needs a denominator of transfers we caused and "
                                         "precision needs a known cause, so these three exist "
                                         "only for phase A (gate rule 8)"),
        },
        "instrument": {**{k: v for k, v in inst.items() if k not in ("command", "capture")},
                       "capture": capture},
    }


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
           "--registry", args.registry, "--out", args.out,
           "--pass", getattr(args, "pass_name", "sequential")]
    if getattr(args, "bench", False):
        cmd.append("--bench")
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

    bv = sub.add_parser("bench-verify",
                        help="phase A instrument metrics: recall, precision, false provenance")
    bv.add_argument("--run", default="latest", help="'latest' or a path to runs/<id>")
    bv.add_argument("--truth", default=None,
                    help="the bench's own ledger (default: <run>/bench_truth.jsonl)")
    bv.set_defaults(func=_cmd_bench_verify)

    dc = sub.add_parser("disclosure-check",
                        help="gate rule 7: destinations of a run that nobody declared")
    dc.add_argument("--run", default="latest", help="'latest' or a path to runs/<id>")
    dc.add_argument("--declared", default=None,
                    help="the declaration file (default: registry/declared-destinations.json)")
    dc.set_defaults(func=_cmd_disclosure_check)

    f = sub.add_parser("figures", help="write a run's normalized aggregate to docs/figures/")
    f.add_argument("--run", default="latest", help="'latest' or a path to runs/<id>")
    f.add_argument("--out", default="docs/figures", help="directory for the committed artifact")
    f.set_defaults(func=_cmd_figures)

    r = sub.add_parser("run", help="drive the pinned servers under capture (needs Docker)")
    r.add_argument("--registry", default="registry/servers.yaml")
    r.add_argument("--out", default="runs/")
    r.add_argument("--only", action="append", default=[], metavar="ID",
                   help="drive only these server ids (repeatable), for a smoke test")
    r.add_argument("--pass", dest="pass_name", default="sequential",
                   choices=["sequential", "concurrent"],
                   help="which phase B pass to drive (default: sequential). The two are separate "
                        "runs and separate published figures; see docs/PHASES.md, phase B.")
    r.add_argument("--bench", action="store_true",
                   help="phase A: drive concurrent waves against our own bench server and sink")
    r.set_defaults(func=_cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
