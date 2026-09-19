"""The browser control: drive a bare headless browser through the proxy, with no MCP server.

Run inside the harness container by run.sh, after mitmdump is up, exactly where drive_all.py runs
in a phase B pass. It exists to turn one sentence of diagnosis into one measurement.

THE QUESTION. A phase B pass flagged destinations on a server that embeds a headless browser, and
the plausible reading was "the browser checks for updates on its own, the server never asked for
it". Plausible is not measured. This driver launches the SAME browser binary with the SAME flags
through the SAME proxy, navigating to the SAME URL, with no MCP server in the process tree at all,
and records where it goes. `mcpfanout.control.compare` then puts the two destination sets side by
side. If the flagged hosts are in both, the cause is attributed to the component by measurement;
if they are not, the diagnosis was wrong and the finding stands against the server.

WHAT IS HELD CONSTANT, and why each one is not a detail:

  - The binary. Not a distribution browser from the image: the exact build the MCP server's own
    package downloaded into its cache, found rather than installed, so the control cannot be a
    different browser than the one under measurement.
  - The launch flags. The server's package chooses `--no-sandbox --single-process --no-zygote`
    when DOCKER_CONTAINER is set (registry/servers.yaml records this, read from the package's own
    dist/index.js). A control run with different flags would be a different browser process.
  - The proxy path. Via HTTP(S)_PROXY in the environment, NOT via --proxy-server, because that is
    how the server's browser receives it (harness/drive_all.py builds that environment) and the
    two routes do not resolve proxies identically for every request a browser makes.
  - The navigation target. Read from corpus/calls/puppeteer.json, never copied here, so the
    control cannot drift from the corpus call it is the control FOR.
  - The argument digests. Published to the capture addon exactly as the driver publishes them for
    a real call, so the control's flows are matched against the same material. A browser
    background request that matched our corpus arguments would be a far more serious finding than
    the one under investigation, and this is what would show it.

WHAT IS DELIBERATELY NOT HELD CONSTANT: the number of launches. The background destination set
varies between browser starts (one earlier capture produced a host two others did not), so a
single draw of either condition proves nothing about a host it happens to miss. The control is
driven with REPETITIONS and compared as a union, with per-repetition counts kept.

A COLD PROFILE PER REPETITION. Each launch gets a fresh --user-data-dir, because the server's
browser gets one too: a warm profile suppresses exactly the first-run traffic under investigation,
which would produce a clean control for the wrong reason.

Standard library only. This file imports the measurement core for its record shapes and for the
control-file protocol, and nothing else: two writers of the addon's control file with two notions
of its shape is how the addon ends up reading a payload nobody wrote.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from mcpfanout.control import CONTROL_SERVER_ID
from mcpfanout.driver import CallSpec, args_digests_for, publish_active_calls
from mcpfanout.record import (PASS_CONTROL, PHASE_DRAINED, PHASE_DRIVING, RunManifest, ToolCall,
                              write_jsonl, write_manifest)
from mcpfanout.redact import DEFAULT_SALT, Redactor
from mcpfanout.shingle import DEFAULT_K, DEFAULT_W

# The flags the MCP server's package passes when it detects a container, transcribed from
# registry/servers.yaml where they were read out of the package's own dist/index.js. Transcribed
# and not imported because the registry is YAML and this stays standard-library only;
# tests/test_control.py fails if this list and the registry's record of it ever diverge,
# which is the drift guard that makes one copy safe.
SERVER_BROWSER_FLAGS = ("--no-sandbox", "--single-process", "--no-zygote")

# Where the server's package puts the browser it downloads. Globbed rather than pinned: the build
# number is chosen by the package's own resolution and pinning it here would make the control
# silently use a browser the server does not.
BROWSER_CACHE_GLOB = "chrome/*/chrome-linux64/chrome"

# The corpus the control is the control FOR. The URL is read from it; nothing about the target is
# written in this file.
PUPPETEER_CORPUS = "corpus/calls/puppeteer.json"

DEFAULT_REPETITIONS = 3
DEFAULT_DWELL_S = 12.0
# How long to wait for the browser to exit after SIGTERM before killing it. A browser that ignores
# the term is killed and the repetition is recorded as killed, which is data about the browser,
# not an error in the control.
TERM_GRACE_S = 5.0


def find_browser(cache_root: Path) -> Path:
    """The browser binary the server's package downloaded, or a loud failure.

    A control that could not find the binary and quietly launched nothing would produce an empty
    destination set, which reads as "the bare browser reaches nothing" -- the most misleading
    possible outcome, because it would refute the diagnosis by measuring nothing at all.
    """
    matches = sorted(cache_root.glob(BROWSER_CACHE_GLOB))
    if not matches:
        raise SystemExit(
            f"[control] no browser under {cache_root}/{BROWSER_CACHE_GLOB}. The control must use "
            f"the same binary the server uses, so it does not install one: warm the server first "
            f"(harness/run.sh does this before the proxy starts) and re-run.")
    # Newest by path order, which is the build directory name. If several exist the run records
    # which one was used, so a reader is never left guessing.
    return matches[-1]


def navigation_target(corpus_path: Path) -> tuple[str, dict]:
    """The URL the corpus navigates to, and the full argument dict it travels in.

    Both, not just the URL: the digests published to the addon must be the digests of the whole
    argument object, because that is what driver.args_bytes hashes for a real call. Publishing the
    digests of a bare URL string would ask the matcher a question the capture never asks.
    """
    calls = json.loads(corpus_path.read_text(encoding="utf-8"))
    for call in calls:
        args = call.get("arguments") or {}
        if "url" in args:
            return str(args["url"]), dict(args)
    raise SystemExit(f"[control] {corpus_path} has no call carrying a url argument; there is "
                     f"nothing to be the control for")


def one_launch(browser: Path, url: str, *, proxy: str, dwell_s: float,
               profile_dir: Path) -> tuple[bool, str]:
    """Launch the browser once, let it sit, then stop it. Returns (exited_cleanly, note).

    The dwell is the measurement window and it is not a sleep for convenience: the traffic under
    investigation is background traffic, which by definition does not happen during page load. A
    control that killed the browser the moment the document was ready would miss precisely the
    class of request it exists to observe.
    """
    env = dict(os.environ)
    env.update({"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy,
                "http_proxy": proxy, "https_proxy": proxy})
    cmd = [str(browser), "--headless=new", *SERVER_BROWSER_FLAGS,
           f"--user-data-dir={profile_dir}", url]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        deadline = time.monotonic() + dwell_s
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                # It exited on its own before the dwell was up. Recorded, because a browser that
                # exits early has a shorter observation window than one that does not, and the
                # comparison is about what was OBSERVABLE, not about what we intended.
                return True, f"exited on its own after {dwell_s - (deadline - time.monotonic()):.1f}s"
            time.sleep(0.25)
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=TERM_GRACE_S)
            return True, f"terminated after the {dwell_s:.0f}s dwell"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=TERM_GRACE_S)
            return False, f"ignored SIGTERM after the {dwell_s:.0f}s dwell and was killed"
    finally:
        if proc.poll() is None:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--proxy", default="http://127.0.0.1:8080")
    ap.add_argument("--salt", default="")
    ap.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    ap.add_argument("--dwell", type=float, default=DEFAULT_DWELL_S)
    ap.add_argument("--corpus", default=PUPPETEER_CORPUS)
    ap.add_argument("--browser-cache", default=str(Path.home() / ".cache" / "puppeteer"))
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    control_dir = run_dir / "control"
    corpus_path = Path(args.corpus)
    url, arguments = navigation_target(corpus_path)
    browser = find_browser(Path(args.browser_cache))
    salt = args.salt.encode() or DEFAULT_SALT
    redactor = Redactor(salt=salt, k=DEFAULT_K, w=DEFAULT_W)
    digests = args_digests_for(CallSpec(tool_name="navigate", arguments=arguments), redactor)
    run_id = run_dir.name

    print(f"[control] browser: {browser}")
    print(f"[control] target read from {corpus_path}")
    print(f"[control] {args.repetitions} launches, {args.dwell:.0f}s dwell each, "
          f"cold profile per launch, no MCP server")

    calls: list[ToolCall] = []
    for i in range(args.repetitions):
        call_id = f"control-c{i:03d}"
        # Published exactly as the driver publishes a real in-flight call, so the addon does the
        # same matching and the same attribution it does under capture. The traceparent is empty
        # and not a fresh one: we set no _meta on anything here, and publishing a traceparent we
        # never sent would let a flow claim propagation that never happened.
        publish_active_calls(control_dir, run_id, CONTROL_SERVER_ID, [{
            "call_id": call_id, "traceparent": "", "args_present": True,
            "args_digests": digests,
        }], phase=PHASE_DRIVING)
        with tempfile.TemporaryDirectory(prefix="control-profile-") as profile:
            ok, note = one_launch(browser, url, proxy=args.proxy, dwell_s=args.dwell,
                                  profile_dir=Path(profile))
        publish_active_calls(control_dir, run_id, CONTROL_SERVER_ID, [], phase=PHASE_DRAINED)
        print(f"[control] launch {i + 1}/{args.repetitions}: {note}")
        calls.append(ToolCall(run_id, CONTROL_SERVER_ID, call_id, "navigate", True, "",
                              ok=ok, error="" if ok else note, wave_size=1))

    # How the control was driven, as data rather than as flags somebody has to remember. The
    # comparison reads this for its provenance block, so publishing the figure from the host
    # cannot describe a dwell or a repetition count the run was not driven with.
    (run_dir / "control-driving.json").write_text(json.dumps({
        "repetitions": args.repetitions,
        "dwell_seconds": args.dwell,
        "browser": str(browser),
        "flags": list(SERVER_BROWSER_FLAGS),
        "headless": "--headless=new",
        "cold_profile_per_launch": True,
        "proxy_via": "HTTP(S)_PROXY environment, as the server's browser receives it",
        "navigation_url_source": str(corpus_path),
        "mcp_server_in_process_tree": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    write_jsonl(run_dir / "calls.jsonl", calls)
    write_manifest(run_dir / "manifest.json", RunManifest(
        run_id=run_id, created=datetime.now(timezone.utc).isoformat(),
        salt_fixed=(salt == DEFAULT_SALT), k=DEFAULT_K, w=DEFAULT_W,
        corpus_sha256=hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        server_ids=[CONTROL_SERVER_ID], pass_name=PASS_CONTROL,
        tool_versions={"browser": str(browser)},
        notes=(f"CONTROL run, not a measurement of any server. A bare headless browser launched "
               f"{args.repetitions} times with the flags {' '.join(SERVER_BROWSER_FLAGS)} through "
               f"the capture proxy, navigating to the target in {corpus_path}, with no MCP server "
               f"in the process tree. The six numbers are NOT computed from this run and must not "
               f"be: it has no tool calls. Its only product is the destination-set comparison, "
               f"`python -m mcpfanout.cli control-compare`. See src/mcpfanout/control.py."),
    ))
    print(f"[control] wrote {len(calls)} control navigations to {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
