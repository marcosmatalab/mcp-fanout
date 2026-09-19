"""Command line entry point.

Subcommands:
  aggregate  Compute the six numbers from a run (the rule-6 commands behind the Makefile).
  figures    Write a run's normalized aggregate to docs/figures/ as a committed artifact.
  bench-verify  Phase A instrument metrics (recall, precision, false provenance).
  calibrate  F1.1: the matcher's false-positive rate on structured language that shares no
             information. `--half held_out` is the published figure; the calibration half is for
             tuning and the two may not be swapped (docs/CALIBRATION.md).
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


def _shingle_default_k() -> int:
    """The shipped k, read from where it is defined rather than repeated as a literal here."""
    from .shingle import DEFAULT_K
    return DEFAULT_K


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


def _cmd_calibrate(args: argparse.Namespace) -> int:
    """F1.1: measure how often the matcher claims a coincidence that does not exist.

    The purpose is derived from the half rather than taken as a flag, and that is the whole safety
    property: the held-out half is only ever loaded for publication, the calibration half only for
    calibration. A `--purpose` flag would put the choice in the hands of whoever is in a hurry.
    """
    from .calibrate import (CALIBRATION, HELD_OUT, PURPOSE_CALIBRATION, PURPOSE_PUBLICATION,
                            false_positive_rate, load_negative)
    from .redact import Redactor

    purpose = PURPOSE_PUBLICATION if args.half == HELD_OUT else PURPOSE_CALIBRATION
    corpus = load_negative(args.half, purpose=purpose)
    out = false_positive_rate(corpus, Redactor(k=args.k))
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.out:
        # Committed alongside the prose that quotes it, so the figure cannot drift from the text.
        # Named by half, k and weighting, because those three are what make two of these figures
        # incomparable, and a single file would quietly overwrite the baseline with a tuned run.
        weight = "weighted" if out.get("rarity_weighting") else "unweighted"
        name = f"fp-{args.half.replace('_', '-')}-k{args.k}-{weight}.json"
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {dest / name}", file=sys.stderr)
    return 0


def _cmd_prep_positive(args: argparse.Namespace) -> int:
    """Distil the phase A positive control out of a bench run's own ledger. Run once per bench change.

    Why the fixture is committed rather than read from the run. Gate rule 4 refuses to track runs,
    so a curve computed straight off runs/<id> would be re-derivable only by someone with Docker,
    a network, and the patience to reproduce a capture. The material here is the BENCH's own
    synthetic payloads, keyed from a published constant, with no third-party content in it at all,
    so committing it costs nothing the doctrine protects and makes `make ksweep` reproducible
    anywhere, including CI. The alternative, re-running the bench once per value of k, is 57 Docker
    runs to answer a question the sender already knows the answer to.
    """
    import base64
    run_dir = _resolve_run(args.run)
    truth_path = Path(args.truth) if args.truth else run_dir / "bench_truth.jsonl"
    if not truth_path.is_file():
        sys.exit(f"error: {truth_path} not found; --run must be a bench run")

    rows = [json.loads(line) for line in truth_path.read_text().splitlines() if line.strip()]
    missing = [r for r in rows if "request_body_b64" not in r]
    if missing:
        sys.exit(f"error: {len(missing)} ledger rows carry no request bytes. This run predates "
                 f"bench/server.py recording them; re-run `make bench`.")

    transfers = []
    for i, r in enumerate(rows):
        if r.get("error"):
            continue  # a transfer that failed to send carried nothing; it is not a positive
        transfers.append({
            "transfer_id": f"t{i:03d}",
            "channel": r["channel"],
            "arguments": r.get("call_arguments") or {},
            "target": r.get("request_target", r.get("path", "")),
            "body_b64": r.get("request_body_b64", ""),
            # The bench's own design decides this, not the matcher, and there are THREE cases and
            # not two. A transfer is detectable only if it went through a channel the matcher reads
            # AND carried something to find. Collapsing the other two would put 17 transfers that
            # carried nothing at all in the same bucket as the 8 that carried material through a
            # channel byte-literal matching cannot read, and only the second bucket is what
            # negative 3 costs.
            "detectable_by_design": r["channel"] in ("target", "body") and bool(r.get("fragment")),
            "not_detectable_reason": (
                "" if (r["channel"] in ("target", "body") and r.get("fragment"))
                else "channel_not_read" if r["channel"] == "header"
                else "re_encoded" if r["channel"].startswith("body:")
                else "nothing_carried"),
        })
    payload = {
        "_what_this_is": ("Phase A positive control: every transfer the bench actually made, with "
                          "the bytes it sent and the arguments of the call that caused it. Distilled "
                          "from the bench's OWN ledger, which it writes from inside its handler. "
                          "Used by the k sweep as the truth pattern (docs/CALIBRATION.md)."),
        "_why_committed": ("the bench's payloads are synthetic and keyed from a published constant, "
                           "so this file carries no third-party content and makes the sweep "
                           "reproducible without Docker. It is not a run: gate rule 4 still holds"),
        "source_run": run_dir.name,
        "transfers": transfers,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    detectable = sum(1 for t in transfers if t["detectable_by_design"])
    print(f"wrote {out}: {len(transfers)} transfers, {detectable} detectable by design")
    return 0


def _cmd_ksweep(args: argparse.Namespace) -> int:
    """F1.2: the false-positive and recall curves against k, and the k the rule picks.

    Runs on the calibration half only, and says so in two places: the loader is asked for that half
    by name, and sweep_k refuses any other. Choosing a parameter is calibration by definition.
    """
    from .calibrate import (CALIBRATION, PURPOSE_CALIBRATION, load_negative, load_positive,
                            sweep_k)
    corpus = load_negative(CALIBRATION, purpose=PURPOSE_CALIBRATION)
    transfers = load_positive(args.positive)
    out = sweep_k(corpus, transfers, k_min=args.k_min, k_max=args.k_max)
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.out:
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / "ksweep-calibration.json"
        path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)
    return 0


def _cmd_inventory(args: argparse.Namespace) -> int:
    """The self-match ceiling and its decomposition: what the sensor can see of realistic material.

    Runs on the calibration half. It is a descriptive inventory rather than a tuning step, but it is
    read while working on the matcher, so it uses the half that is there to be read.
    """
    from .calibrate import (CALIBRATION, PURPOSE_CALIBRATION, detectability_inventory,
                            load_negative, load_positive)
    from .redact import Redactor
    corpus = load_negative(CALIBRATION, purpose=PURPOSE_CALIBRATION)
    out = detectability_inventory(corpus, load_positive(args.positive), Redactor(k=args.k))
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.out:
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"inventory-k{args.k}.json"
        path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)
    return 0


def _cmd_rarity(args: argparse.Namespace) -> int:
    """F1.3: measure whether rarity weighting lowers the false-positive rate, and say what it implies.

    Exit code carries the verdict: 0 if the rate fell (the weighting earns its place), 1 if it did
    not (revert it and document why). A measurement whose conclusion needs a human to read the prose
    is a measurement that gets quoted the other way round eventually.
    """
    from .rarity import VERDICT_KEPT, acceptance
    from .shingle import DEFAULT_K
    out = acceptance(shipped_k=args.k, probe_k=args.probe_k)
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.out:
        dest = Path(args.out)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"rarity-acceptance-k{args.k}.json"
        path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)
    return 0 if out["verdict"] == VERDICT_KEPT else 1


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
    # The package-infrastructure list is the declared, versioned, cited answer to "is this host a
    # package registry". Branch one of gate rule 7's procedure needs it, and inferring it from a
    # hostname instead would be the plausible guess this repository keeps finding in its history.
    report = check(run.flows, declared, ExclusionList.load(PACKAGE_INFRASTRUCTURE_PATH))
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

    cal = sub.add_parser("calibrate",
                         help="F1.1: the matcher's false-positive rate on structured language")
    cal.add_argument("--half", required=True, choices=["calibration", "held_out"],
                     help="held_out is the published figure and is measured once, at the end")
    cal.add_argument("--k", type=int, default=_shingle_default_k(),
                     help="k-gram length to measure at (default: the shipped constant)")
    cal.add_argument("--out", default=None,
                     help="directory to write the figure into, e.g. docs/figures/calibration")
    cal.set_defaults(func=_cmd_calibrate)

    pp = sub.add_parser("prep-positive",
                        help="distil the phase A positive control from a bench run's ledger")
    pp.add_argument("--run", default="latest", help="'latest' or a path to a BENCH runs/<id>")
    pp.add_argument("--truth", default=None, help="the ledger (default: <run>/bench_truth.jsonl)")
    pp.add_argument("--out", default="corpus/positive/bench-transfers.json")
    pp.set_defaults(func=_cmd_prep_positive)

    ks = sub.add_parser("ksweep", help="F1.2: false positives and recall against k, and the choice")
    ks.add_argument("--positive", default="corpus/positive/bench-transfers.json")
    ks.add_argument("--k-min", type=int, default=8)
    ks.add_argument("--k-max", type=int, default=64)
    ks.add_argument("--out", default=None, help="directory for the committed curve")
    ks.set_defaults(func=_cmd_ksweep)

    inv = sub.add_parser("inventory",
                         help="the self-match ceiling: what the sensor can see of realistic material")
    inv.add_argument("--k", type=int, default=_shingle_default_k())
    inv.add_argument("--positive", default="corpus/positive/bench-transfers.json")
    inv.add_argument("--out", default=None)
    inv.set_defaults(func=_cmd_inventory)

    ra = sub.add_parser("rarity", help="F1.3: does rarity weighting lower the false-positive rate")
    ra.add_argument("--k", type=int, default=_shingle_default_k(),
                    help="the shipped k: where the published comparison is made")
    ra.add_argument("--probe-k", type=int, default=16,
                    help="a k at which false positives still exist, so the mechanism is observable")
    ra.add_argument("--out", default=None, help="directory for the committed figure")
    ra.set_defaults(func=_cmd_rarity)

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
