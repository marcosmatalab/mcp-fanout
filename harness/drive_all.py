"""Drive every server in the registry through the proxy, writing the run. Two passes, one per run.

Run inside the harness container by run.sh, after mitmdump is up.

TWO PASSES, AND WHY THEY CANNOT BE ONE RUN (docs/PROTOCOL.md, phase B).

  --mode sequential   one call in flight per server, from `corpus_ref`. This is what numbers 1,
                      2, 3 and 4 are read from: fan-out, distinct domains, traceparent
                      propagation and provenance coverage all ask what one invocation does, and
                      asking it with ten invocations in flight would make every per-call figure a
                      figure about our own wave size. Its attribution grades are
                      CONTENT_MATCH_UNCONTESTED by construction, reported as such and never as a
                      result about content matching.

  --mode concurrent   waves of N calls in flight per server, from `concurrent_corpus_ref`, with N
                      climbing the same ladder the phase A bench used (2, 5, 10) capped by the
                      server's declared `max_concurrency`. This is the only condition in which
                      CONTENT_UNIQUE and CONTENT_AMBIGUOUS can occur at all, so it is the only
                      pass number 5 may be read from.

The two write SEPARATE RUNS with the pass recorded in the manifest, and this file refuses to
drive a second pass into an existing run directory. Mixing them would average two experimental
conditions into one distribution, which is the one arithmetic no comment can undo afterwards.

Needs the 'capture' extra (PyYAML). Never computes a number; it only produces calls.jsonl and
manifest.json. Flows are written by the addon.
"""

from __future__ import annotations

import argparse
import os
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml  # from the 'capture' extra

from mcpfanout.driver import (CallSpec, StdioMCPClient, drive, drive_wave,
                              publish_active_calls)
from mcpfanout.record import (PASS_CONCURRENT, PASS_SEQUENTIAL, PHASE_HANDSHAKE,
                              PHASE_LAUNCHER, RunManifest, ToolCall, read_manifest, write_jsonl,
                              write_manifest)
from mcpfanout.redact import DEFAULT_SALT, Redactor
from mcpfanout.shingle import DEFAULT_K, DEFAULT_W

# The concurrency ladder, the same levels the phase A bench drove (bench/waves.json). Same levels
# on purpose: the bench established what the sensor does at N = 2, 5 and 10 with maximally
# distinctive fragments, so driving real servers at other levels would leave the comparison
# without a rung to stand on. Capped per server by max_concurrency and by corpus length.
CONCURRENCY_LADDER = (2, 5, 10)

# One wave of ten calls on a cold npx server can take a while, and a wave that times out is
# recorded as N failed calls, which looks like a server refusing concurrency. Generous on purpose.
WAVE_TIMEOUT_S = 90.0


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
            # Same declared env as the capture pass, minus the proxy: a server warmed under a
            # different configuration is not the server that then gets measured.
            with StdioMCPClient(list(srv["launch"]), server_env(srv, {}),
                                read_timeout=60.0) as client:
                client.initialize(timeout=300.0)
                n = len(client.list_tools())
            print(f"[warm] {sid}: cache populated, {n} tools")
        except Exception as exc:  # a server that cannot start is reported, not fatal: the
            # capture pass records it as zero egress, which is the finding.
            print(f"[warm] {sid}: did not start ({type(exc).__name__}: {exc})")
    return 0


def concurrency_levels(cap: int, corpus_len: int) -> list[int]:
    """Which rungs of the ladder this server is driven at.

    Two limits, both real. ``cap`` is the server's declared ``max_concurrency``, which is a claim
    about the server (a single browser page, a five-step reasoning chain) and carries its reason
    in the registry. ``corpus_len`` is the arithmetic one: a wave of N needs N distinct calls, and
    padding a corpus to reach a rung would mean inventing arguments to fill a number, which is
    the opposite of the realism rule the concurrent corpus is written under
    (corpus/concurrent/README.md).

    Returns the rungs at or below both, so a server with a cap of 2 is driven at N = 2 only and
    is reported as such rather than silently driven at 10.
    """
    limit = min(cap, corpus_len)
    return [n for n in CONCURRENCY_LADDER if n <= limit]


def server_env(srv: dict, proxy_env: dict) -> dict:
    """The proxy environment, this server's declared configuration, and its declared secrets.

    Per-server keys come from the registry's `env` field, which may hold nothing secret (gate rule
    5). They are values cast to strings because YAML will happily give a bool and the environment
    only carries text.

    SECRETS ARE DECLARED BY NAME AND NEVER BY VALUE. `secret_env` in the registry is a list of
    variable NAMES; the values are read from this process's environment, which the operator fills
    from a credential file kept outside the repository. So the registry stays committable and gate
    rule 5 holds: a lab credential exists in the environment and nowhere in the repository.

    An absent secret is passed over in silence HERE and reported loudly elsewhere. Raising would
    make one missing token stop a ten-server run, and defaulting to empty string would hand the
    server a credential-shaped nothing. What must not happen is the third option, which is that
    the run looks credentialed afterwards: `credential_presence` records, per server and per
    declared name, whether the value was there, and the manifest carries it (gate rule 10, an
    absent instrument must not pass quietly).
    """
    extra = {str(k): str(v) for k, v in (srv.get("env") or {}).items()}
    secrets = {}
    for name in (srv.get("secret_env") or []):
        value = os.environ.get(str(name))
        if value:
            secrets[str(name)] = value
    return {**proxy_env, **extra, **secrets}


def credential_presence(selected: list[dict]) -> dict:
    """Per server, which declared secrets were actually available. NAMES AND BOOLEANS ONLY.

    This is what stops an uncredentialed run reading as a credentialed one afterwards, which is
    gate rule 10 applied to a credential: the failure is silent by nature, because a server
    missing its token still starts, still handshakes, and still produces flows. github does
    exactly that and fails only its four search_code calls.

    No value, no prefix, no length: a boolean cannot leak a token, and this dict goes into the
    manifest, which is committed as a figure.
    """
    out = {}
    for srv in selected:
        names = [str(n) for n in (srv.get("secret_env") or [])]
        if names:
            out[srv["id"]] = {n: bool(os.environ.get(n)) for n in names}
    return out


def drive_server_concurrent(srv: dict, *, run_id: str, control_dir: Path, redactor: Redactor,
                            proxy_env: dict) -> tuple[list[ToolCall], list[dict]]:
    """Drive one server as waves of N concurrent calls, climbing the ladder. Returns (calls, waves).

    One client and one server process for the whole ladder, not one per wave. A fresh process per
    wave would hide the case this pass exists to expose: a server that pools connections across
    calls can only be seen pooling them if the calls share its lifetime.

    A wave that raises is recorded as N failed calls and the ladder continues. A server that
    cannot take concurrency is a finding, not a reason to abandon the run: the finding IS that it
    refused, and the error text is what distinguishes "refused" from "timed out" from "crashed".
    """
    sid = srv["id"]
    corpus = load_corpus(Path(srv["concurrent_corpus_ref"]))
    levels = concurrency_levels(int(srv.get("max_concurrency", 1)), len(corpus))
    calls: list[ToolCall] = []
    waves: list[dict] = []

    if not levels:
        print(f"[drive_all] {sid}: no concurrency level fits (cap "
              f"{srv.get('max_concurrency')}, corpus {len(corpus)}); driving nothing")
        return calls, waves

    try:
        _drive_ladder(srv, levels, corpus, run_id=run_id, control_dir=control_dir,
                      redactor=redactor, proxy_env=proxy_env, calls=calls, waves=waves)
    except Exception as exc:
        # Same rule as the sequential path (driver.drive): a server that cannot start is a data
        # point, not a stop. Every call the ladder still owed is recorded as not driven, with the
        # reason, so the run keeps the other nine servers.
        err = f"{type(exc).__name__}: {exc}"
        print(f"[drive_all] {sid}: did not complete its ladder ({err[:200]})")
        index = sum(w["calls"] for w in waves)
        for n in levels:
            done = {w["n"] for w in waves}
            if n in done:
                continue
            for i in range(n):
                spec = corpus[i]
                calls.append(ToolCall(run_id, sid, f"{sid}-c{index + i:03d}", spec.tool_name,
                                      bool(spec.arguments), "", ok=False, error=err, wave_size=n))
            waves.append({"server_id": sid, "n": n, "calls": n, "errored": n})
            index += n
    return calls, waves


def _drive_ladder(srv: dict, levels: list[int], corpus: list[CallSpec], *, run_id: str,
                  control_dir: Path, redactor: Redactor, proxy_env: dict,
                  calls: list[ToolCall], waves: list[dict]) -> None:
    """Climb one server's ladder over one connection, appending to the caller's lists.

    Split out so the caller can wrap it whole and decide what an escaped exception means for the
    record, exactly as driver.drive does with _drive_corpus. One client for the whole ladder, not
    one per wave: a fresh process per wave would hide connection pooling across calls, which is a
    case this pass exists to expose.
    """
    sid = srv["id"]
    index = 0
    # The lifecycle phases, published exactly as driver._drive_corpus publishes them for the
    # sequential pass. This path had neither, and the effect was not a missing label: the control
    # file still held the PREVIOUS server's id with phase `drained`, so `npx -y pkg@ver` resolving
    # THIS server's package was recorded as the previous server's call-caused egress. Measured on
    # the first ten-server concurrent capture, which flagged four servers under gate rule 7 for a
    # package registry none of them contacted, plus one flow attributed to nobody at all (the
    # first server's launcher, before anything had been published). Same defect the sequential
    # path was fixed for; this one was left behind because the two paths publish independently.
    publish_active_calls(control_dir, run_id, sid, [], phase=PHASE_LAUNCHER)
    with StdioMCPClient(list(srv["launch"]), server_env(srv, proxy_env),
                        read_timeout=WAVE_TIMEOUT_S) as client:
        publish_active_calls(control_dir, run_id, sid, [], phase=PHASE_HANDSHAKE)
        client.initialize(timeout=300.0)
        client.list_tools()  # listed for realism and to let servers lazily wire up their tools
        for n in levels:
            # The first n calls of the corpus, deterministically. Not a random sample: a run has
            # to be reproducible (gate rule 1), and a random subset would change the argument
            # overlap between waves, which is the independent variable of this whole pass.
            specs = corpus[:n]
            results = drive_wave(client, specs, run_id=run_id, server_id=sid,
                                 redactor=redactor, control_dir=control_dir,
                                 start_index=index, timeout=WAVE_TIMEOUT_S)
            for r in results:
                calls.append(ToolCall(run_id, sid, r.call_id, r.tool_name, r.args_present,
                                      r.traceparent, ok=r.ok, error=r.error,
                                      stdout_noise_lines=r.stdout_noise_lines, wave_size=n))
            failed = [r for r in results if not r.ok]
            waves.append({"server_id": sid, "n": n, "calls": len(results),
                          "errored": len(failed)})
            print(f"[drive_all] {sid}: wave N={n}, {len(results)} calls"
                  + (f", {len(failed)} errored" if failed else ""))
            for r in failed:
                print(f"[drive_all]   {r.call_id} {r.tool_name}: {r.error[:200]}")
            index += n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--proxy", default="http://127.0.0.1:8080")
    ap.add_argument("--salt", default="")
    ap.add_argument("--mode", choices=[PASS_SEQUENTIAL, PASS_CONCURRENT], default=PASS_SEQUENTIAL,
                    help="which phase B pass to drive. See the module docstring and "
                         "docs/PROTOCOL.md: the two are separate runs and separate figures.")
    ap.add_argument("--only", action="append", default=[], metavar="ID",
                    help="drive only these server ids (repeatable). Default: all of them.")
    ap.add_argument("--warm", action="store_true",
                    help="only populate package caches and exit; run this BEFORE the proxy starts")
    args = ap.parse_args()

    reg = yaml.safe_load(Path(args.registry).read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir)
    control_dir = run_dir / "control"
    # The registry declares k and w for the run, and a test pins them to the shipped constants, so
    # the fallback is the constant rather than a literal copy of last year's value.
    k, w = int(reg.get("k", DEFAULT_K)), int(reg.get("w", DEFAULT_W))
    salt = args.salt.encode() or DEFAULT_SALT
    redactor = Redactor(salt=salt, k=k, w=w)
    run_id = run_dir.name

    # A run holds ONE pass. Refused rather than merged: the aggregate reads the pass off the
    # manifest and reports the grade distribution under it, so a directory holding both passes
    # would publish one distribution over two experimental conditions with a label naming one of
    # them. There is no honest way to read that figure afterwards, which is why this is a hard
    # stop and not a warning.
    existing = run_dir / "manifest.json"
    if existing.is_file():
        prior = read_manifest(existing).pass_name
        if prior and prior != args.mode:
            raise SystemExit(
                f"[drive_all] refusing to drive the {args.mode} pass into {run_dir}: it already "
                f"holds the {prior} pass. One pass per run (docs/PROTOCOL.md, phase B). Point "
                f"--run-dir at a new directory.")

    # Every server process inherits the proxy so its HTTP(S) egress passes through mitmdump.
    proxy_env = {"HTTP_PROXY": args.proxy, "HTTPS_PROXY": args.proxy,
                 "http_proxy": args.proxy, "https_proxy": args.proxy}

    all_calls: list[ToolCall] = []
    server_ids: list[str] = []
    all_waves: list[dict] = []
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

    # Which corpus field this pass reads. Named once, so a server missing it fails loudly here
    # rather than driving the wrong corpus under the right label.
    corpus_field = "corpus_ref" if args.mode == PASS_SEQUENTIAL else "concurrent_corpus_ref"
    missing = [s["id"] for s in selected if not s.get(corpus_field)]
    if missing:
        raise SystemExit(f"[drive_all] {args.mode} pass needs {corpus_field} and these servers "
                         f"have none: {missing}")

    print(f"[drive_all] pass: {args.mode}")
    for srv in selected:
        sid = srv["id"]
        server_ids.append(sid)
        corpus_hash.update(Path(srv[corpus_field]).read_bytes())

        if args.mode == PASS_CONCURRENT:
            calls, waves = drive_server_concurrent(
                srv, run_id=run_id, control_dir=control_dir, redactor=redactor,
                proxy_env=proxy_env)
            all_calls += calls
            all_waves += waves
            noise = sum(c.stdout_noise_lines for c in calls)
            if noise:
                print(f"[drive_all] {sid}: {noise} non-JSON-RPC lines on stdout "
                      f"(the server is corrupting its own protocol channel; recorded per call)")
            continue

        corpus = load_corpus(Path(srv["corpus_ref"]))
        results = drive(
            command=list(srv["launch"]), corpus=corpus, run_id=run_id, server_id=sid,
            env=server_env(srv, proxy_env), redactor=redactor, control_dir=control_dir,
        )
        for r in results:
            # Every field of DriveResult that ToolCall has, or the record lies by default value:
            # this path dropped ok/error/stdout_noise_lines and the run reported "ok: true,
            # stdout_noise_lines: 0" for calls the driver had just counted 7 noise lines on.
            all_calls.append(ToolCall(run_id, sid, r.call_id, r.tool_name, r.args_present,
                                      r.traceparent, ok=r.ok, error=r.error,
                                      stdout_noise_lines=r.stdout_noise_lines, wave_size=1))
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
    if all_waves:
        # What was actually driven at each rung, per server. Kept beside the run because it names
        # servers, and needed to read the pass at all: a grade distribution at N=10 means nothing
        # if the waves at N=10 errored out. Intent and outcome in one line each, no numbers derived.
        (run_dir / "waves.jsonl").write_text(
            "".join(json.dumps(w, sort_keys=True) + "\n" for w in all_waves), encoding="utf-8")
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
        credential_presence=credential_presence(selected),
        servers_expecting_egress=[s["id"] for s in selected if s.get("expects_egress")],
        pass_name=args.mode,
        notes=(f"Capture run, {args.mode} pass. See docs/PROTOCOL.md before publishing any number."
               + (" Numbers 1 to 4 are read from this pass; its attribution grades are "
                  "CONTENT_MATCH_UNCONTESTED by construction." if args.mode == PASS_SEQUENTIAL else
                  f" Waves at N in {list(CONCURRENCY_LADDER)} capped per server; number 5 is read "
                  f"from this pass and numbers 1 and 2 are NOT (a per-call figure under "
                  f"concurrency is a figure about our wave size).")
               + (f" SUBSET RUN: --only {sorted(set(args.only))}; the registry holds "
                  f"{len(reg.get('servers', []))} servers. Not a measurement of the registry."
                  if args.only else "")),
    ))
    print(f"[drive_all] wrote {len(all_calls)} calls across {len(server_ids)} servers to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
