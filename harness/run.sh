#!/usr/bin/env bash
# Orchestrate one capture run: start the terminating proxy, drive the servers through it,
# stop, then compute the six numbers. Written as a shell pipeline on purpose (cli.py delegates
# here) so the moving parts, the proxy, the CA trust, the driver, the aggregation, are visible
# in one auditable file rather than hidden behind a Python wrapper.
#
# This script assumes it runs INSIDE the harness container (see Dockerfile), where Docker gives
# it an isolated network and no real credentials. Do not run it on a host with live secrets.
set -euo pipefail

REGISTRY="registry/servers.yaml"
OUT_ROOT="runs"
ONLY=()
BENCH=0
# The browser control (src/mcpfanout/control.py): drive a bare headless browser through the same
# proxy with NO MCP server, so that "the destination is the embedded browser's, not the server's"
# becomes a measured attribution instead of a plausible reading of a hostname.
CONTROL=0
CONTROL_AGAINST="latest-sequential"
CONTROL_REPETITIONS=3
CONTROL_DWELL=12
CONTROL_AUTHORISATION=""
CONTROL_SERVER="puppeteer"
# Which phase B pass to drive. One run holds one pass and the run id says which, because the two
# are separate experimental conditions whose figures are published separately (docs/PROTOCOL.md,
# phase B). drive_all.py refuses to write a second pass into a run that already holds one.
PASS="sequential"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --registry) REGISTRY="$2"; shift 2 ;;
    --out) OUT_ROOT="$2"; shift 2 ;;
    --only) ONLY+=(--only "$2"); shift 2 ;;
    --pass) PASS="$2"; shift 2 ;;
    --bench) BENCH=1; shift ;;
    --control) CONTROL=1; shift ;;
    --against) CONTROL_AGAINST="$2"; shift 2 ;;
    --repetitions) CONTROL_REPETITIONS="$2"; shift 2 ;;
    --dwell) CONTROL_DWELL="$2"; shift 2 ;;
    --authorisation) CONTROL_AUTHORISATION="$2"; shift 2 ;;
    --control-server) CONTROL_SERVER="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
if [[ "${BENCH}" == "1" && "${CONTROL}" == "1" ]]; then
  echo "[run] --bench and --control are different experiments; pick one" >&2; exit 2
fi
case "${PASS}" in
  sequential|concurrent) ;;
  *) echo "[run] --pass must be sequential or concurrent, got: ${PASS}" >&2; exit 2 ;;
esac

# Refuse to run outside a container. The header above says this script assumes it is inside one,
# but saying so is not enforcing it: below, this script copies a CA into
# /usr/local/share/ca-certificates and runs update-ca-certificates, which on a host would modify
# the operator's own trust store. Gate rule 5 ("nothing runs outside the container") has to be a
# check, not a comment. MCPFANOUT_ALLOW_HOST=1 overrides, for someone who has read this and means
# it; there is no path where we modify a host trust store because a wrapper called us by mistake.
if [[ "${MCPFANOUT_ALLOW_HOST:-0}" != "1" && ! -f /.dockerenv && ! -f /run/.containerenv ]]; then
  echo "[run] refusing to run outside a container: this script installs a CA into the system" >&2
  echo "[run] trust store (gate rule 5). Use 'python -m mcpfanout.cli run', which builds and" >&2
  echo "[run] runs the harness image, or set MCPFANOUT_ALLOW_HOST=1 if you really mean it." >&2
  exit 3
fi

# The pass is in the RUN ID, not only in the manifest. The committed figure is named after the
# run, so a directory listing of docs/figures/ says which condition produced each artifact without
# opening any of them; a timestamp alone would leave two incomparable figures looking like a pair.
if [[ "${BENCH}" == "1" ]]; then LABEL="bench"
elif [[ "${CONTROL}" == "1" ]]; then LABEL="control"
else LABEL="${PASS}"; fi
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-${LABEL}"
RUN_DIR="${OUT_ROOT%/}/${RUN_ID}"
mkdir -p "${RUN_DIR}/control"
echo "[run] run dir: ${RUN_DIR} (pass: ${LABEL})"

# Salt: fixed default for a reproducible measurement. Override MCPFANOUT_SALT for a real deployment.
export MCPFANOUT_SALT="${MCPFANOUT_SALT:-mcp-fanout/fixed-salt/v1}"
export MCPFANOUT_RUNDIR="${RUN_DIR}"
export MCPFANOUT_RUNID="${RUN_ID}"
export MCPFANOUT_CONTROL="${RUN_DIR}/control"
export MCPFANOUT_CONTEXT="${RUN_DIR}/context.json"
# k and w come from the shipped constants rather than being repeated here. They were literals for
# one release and that was a defect waiting: k is chosen by a measurement (docs/CALIBRATION.md,
# F1.2), and a capture run that kept its own copy of the old value would have silently matched at a
# k no published figure describes. tests/test_negative_corpus.py fails if the registry and the
# constant disagree; this reads the constant itself, so there is no third copy to drift.
export MCPFANOUT_K="$(python -c 'from mcpfanout.shingle import DEFAULT_K; print(DEFAULT_K)')"
export MCPFANOUT_W="$(python -c 'from mcpfanout.shingle import DEFAULT_W; print(DEFAULT_W)')"
echo "[run] matcher: k=${MCPFANOUT_K} w=${MCPFANOUT_W}"

# 1. Pre-digest the session context (content-free) for the addon.
python -m mcpfanout.cli prep-context --context-dir corpus/context --out "${MCPFANOUT_CONTEXT}"

# 1a-bench. Phase A needs its destinations to resolve and its sink to be listening, both before
#           the proxy starts. The hostnames are staged in the image (one per call, all loopback)
#           and appended here because /etc/hosts cannot be baked into a layer.
if [[ "${BENCH}" == "1" ]]; then
  cat /etc/hosts.bench >> /etc/hosts
  python bench/sink.py --host 127.0.0.1 --port 8099 >"${RUN_DIR}/sink.log" 2>&1 &
  SINK_PID=$!
  trap 'kill "${SINK_PID}" 2>/dev/null || true' EXIT
  for _ in $(seq 1 40); do
    python -c "import socket,sys; s=socket.create_connection(('127.0.0.1',8099),0.25); s.close()" \
      2>/dev/null && break
    sleep 0.25
  done
  echo "[run] bench sink up on 127.0.0.1:8099"
fi

# 1b. Populate the npx/uv package caches BEFORE the proxy exists. Without this, the installer's
#     own downloads pass through mitmdump and are recorded as the server's fan-out: the first
#     working smoke run of `fetch` captured 129 flows, all of them uvx talking to pypi.org and
#     files.pythonhosted.org, and none from the tool call. See drive_all.warm() for the
#     trade-off (this launch is unobserved) and docs/THREATS.md threat 10.
if [[ "${BENCH}" == "1" ]]; then
  echo "[run] bench mode: no package caches to warm, the bench server is ours"
elif [[ "${CONTROL}" == "1" ]]; then
  # The control drives no MCP server, and it still warms one, on purpose. The browser binary the
  # control launches is the one THAT PACKAGE downloads into its cache on install, and the control
  # finds it rather than installing its own: a control that fetched a different build would be a
  # different browser, which is the one thing it may not be. Warming here also keeps the download
  # off camera, exactly as it is in the pass being explained.
  echo "[run] control mode: warming ${CONTROL_SERVER} unproxied, for its browser binary only"
  python harness/drive_all.py --registry "${REGISTRY}" --run-dir "${RUN_DIR}" --warm \
         --only "${CONTROL_SERVER}"
else
  echo "[run] warming package caches (unproxied, before capture starts)"
  python harness/drive_all.py --registry "${REGISTRY}" --run-dir "${RUN_DIR}" --warm \
         "${ONLY[@]+"${ONLY[@]}"}"
fi

# 2. Start mitmdump with our addon. First start also generates the CA under ~/.mitmproxy.
echo "[run] starting mitmdump on :8080"
mitmdump -s src/mcpfanout/capture_addon.py \
         --listen-port 8080 \
         --set stream_large_bodies=1m \
         --set flow_detail=0 \
         >"${RUN_DIR}/mitmdump.log" 2>&1 &
MITM_PID=$!
trap 'kill "${MITM_PID}" 2>/dev/null || true' EXIT

# 3. Wait for the CA, then trust it so node and python servers accept the interception.
CA="${HOME}/.mitmproxy/mitmproxy-ca-cert.pem"
for _ in $(seq 1 30); do [[ -f "${CA}" ]] && break; sleep 0.5; done
if [[ ! -f "${CA}" ]]; then echo "[run] CA not generated; aborting" >&2; exit 1; fi
cp "${CA}" /usr/local/share/ca-certificates/mitmproxy.crt || true
update-ca-certificates >/dev/null 2>&1 || true
export SSL_CERT_FILE="${CA}"
export REQUESTS_CA_BUNDLE="${CA}"
export NODE_EXTRA_CA_CERTS="${CA}"

# Chromium does NOT read the system trust store: it reads an NSS database under ~/.pki/nssdb. So
# update-ca-certificates above is invisible to it and puppeteer's navigations fail with
# ERR_CERT_AUTHORITY_INVALID, which records zero egress for a browser that did try to leave.
# Measured on the third ten-server capture. Rejected alternative: launch Chrome with
# --ignore-certificate-errors, which would be a weaker browser than the one under measurement and
# would hide a server that legitimately refuses a bad certificate. Trusting our own CA in the store
# the browser actually reads changes nothing about how it validates.
mkdir -p "${HOME}/.pki/nssdb"
certutil -d "sql:${HOME}/.pki/nssdb" -N --empty-password >/dev/null 2>&1 || true
certutil -d "sql:${HOME}/.pki/nssdb" -A -t "C,," -n mitmproxy -i "${CA}" >/dev/null 2>&1 \
  || echo "[run] warning: could not add the CA to the NSS store; browser egress may not be captured" >&2

# 4. Optional connection-count backstop: a pcap catches flows the proxy cannot read
#    (non-HTTP, or a pinned client). Reconciliation is left to a follow-up; the pcap is the
#    honest record that the proxy's fan-out count is a lower bound.
if command -v tcpdump >/dev/null 2>&1; then
  tcpdump -i any -w "${RUN_DIR}/backstop.pcap" -q 'tcp' >/dev/null 2>&1 &
  TCPDUMP_PID=$!
  trap 'kill "${MITM_PID}" "${TCPDUMP_PID}" 2>/dev/null || true' EXIT
fi

# 5. Drive. Bench mode drives CONCURRENT waves against our own server; the phenomenon mode
#    drives the registry sequentially.
if [[ "${BENCH}" == "1" ]]; then
  python bench/drive_bench.py --run-dir "${RUN_DIR}" \
         --truth "${RUN_DIR}/bench_truth.jsonl" \
         --proxy "http://127.0.0.1:8080" --salt "${MCPFANOUT_SALT}" --sink-port 8099
elif [[ "${CONTROL}" == "1" ]]; then
  python harness/control_browser.py --run-dir "${RUN_DIR}" \
         --proxy "http://127.0.0.1:8080" --salt "${MCPFANOUT_SALT}" \
         --repetitions "${CONTROL_REPETITIONS}" --dwell "${CONTROL_DWELL}"
else
  python harness/drive_all.py --registry "${REGISTRY}" --run-dir "${RUN_DIR}" \
         --mode "${PASS}" \
         --proxy "http://127.0.0.1:8080" --salt "${MCPFANOUT_SALT}" "${ONLY[@]+"${ONLY[@]}"}"
fi

# 6. Stop capture cleanly so the addon flushes flows.jsonl in its done() hook.
kill -TERM "${MITM_PID}" 2>/dev/null || true
wait "${MITM_PID}" 2>/dev/null || true
[[ -n "${TCPDUMP_PID:-}" ]] && kill "${TCPDUMP_PID}" 2>/dev/null || true

# 7-control. A control run has no tool calls, so the six numbers are not defined over it and the
#            aggregate refuses to compute them (cli._refuse_a_control_run). Its one product is the
#            destination-set comparison against the pass it is explaining. A non-zero exit here is
#            the RESULT, not a failure: it says the bare browser did not reach what the server was
#            flagged for, which leaves the finding pointed at the server.
if [[ "${CONTROL}" == "1" ]]; then
  # No --publish here, and the reason is the container boundary rather than a policy: only runs/,
  # registry/ and corpus/ are bind-mounted (harness/docker-compose.yml), so an artifact written to
  # docs/figures/ from inside would land in the image layer and vanish with the container. The
  # comparison is recomputed on the host, from the run this writes into the mounted runs/, by
  # `make control-publish`. That also puts the authorisation step where a human is, which is where
  # gate rule 7 wants it.
  if [[ -n "${CONTROL_AUTHORISATION}" ]]; then
    echo "[run] note: --authorisation is recorded for the operator; publishing happens on the" >&2
    echo "[run] host with 'make control-publish AUTH=...', because docs/ is not mounted here." >&2
  fi
  set +e
  python -m mcpfanout.cli control-compare --run "${RUN_DIR}" --against "${CONTROL_AGAINST}" \
         --server "${CONTROL_SERVER}" --dwell "${CONTROL_DWELL}"
  CC_STATUS=$?
  set -e
  if [[ "${CC_STATUS}" != "0" ]]; then
    echo "[run] ============================================================" >&2
    echo "[run] THE CONTROL DID NOT EXPLAIN THE FINDING. At least one host" >&2
    echo "[run] the server was flagged for was NOT reached by the bare" >&2
    echo "[run] browser. Read ${RUN_DIR}/control-compare.json before" >&2
    echo "[run] publishing anything that attributes it to the browser." >&2
    echo "[run] ============================================================" >&2
  fi
  echo "[run] done: ${RUN_DIR}/control-compare.json"
  exit 0
fi

# 7. Compute the numbers. Rule 6: these are the commands behind the published figures.
python -m mcpfanout.cli aggregate --run "${RUN_DIR}" --number all | tee "${RUN_DIR}/numbers.json"
if [[ "${BENCH}" == "1" ]]; then
  # The instrument block, which exists only for a bench run: recall and precision have no
  # denominator anywhere else (gate rule 8).
  python -m mcpfanout.cli bench-verify --run "${RUN_DIR}" \
         | tee "${RUN_DIR}/instrument.json" || true
  echo "[run] done: ${RUN_DIR}/numbers.json and ${RUN_DIR}/instrument.json"
else
  echo "[run] done: ${RUN_DIR}/numbers.json"
fi

# 8. Gate rule 7, as a command rather than as a thing to remember. It reduces the run's
#    destinations to the ones nobody declared (registry/declared-destinations.json) and exits
#    non-zero if any server needs reviewing. Not fatal here: the capture already happened and the
#    records are on disk. What it gates is PUBLISHING, so it shouts instead of deleting a run.
#    Its report names servers and hosts, so it stays inside the run directory (gate rule 3).
if ! python -m mcpfanout.cli disclosure-check --run "${RUN_DIR}" >/dev/null; then
  echo "[run] ============================================================" >&2
  echo "[run] GATE RULE 7: at least one destination was not declared, or a" >&2
  echo "[run] server has no declaration. STOP before publishing anything" >&2
  echo "[run] from this run. See ${RUN_DIR}/disclosure.json and read the" >&2
  echo "[run] documentation of each listed server for the listed hosts." >&2
  echo "[run] ============================================================" >&2
fi
