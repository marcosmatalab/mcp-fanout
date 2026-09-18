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
while [[ $# -gt 0 ]]; do
  case "$1" in
    --registry) REGISTRY="$2"; shift 2 ;;
    --out) OUT_ROOT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${OUT_ROOT%/}/${RUN_ID}"
mkdir -p "${RUN_DIR}/control"
echo "[run] run dir: ${RUN_DIR}"

# Salt: fixed default for a reproducible measurement. Override MCPFANOUT_SALT for a real deployment.
export MCPFANOUT_SALT="${MCPFANOUT_SALT:-mcp-fanout/fixed-salt/v1}"
export MCPFANOUT_RUNDIR="${RUN_DIR}"
export MCPFANOUT_RUNID="${RUN_ID}"
export MCPFANOUT_CONTROL="${RUN_DIR}/control"
export MCPFANOUT_CONTEXT="${RUN_DIR}/context.json"
export MCPFANOUT_K="16"
export MCPFANOUT_W="8"

# 1. Pre-digest the session context (content-free) for the addon.
python -m mcpfanout.cli prep-context --context-dir corpus/context --out "${MCPFANOUT_CONTEXT}"

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

# 4. Optional connection-count backstop: a pcap catches flows the proxy cannot read
#    (non-HTTP, or a pinned client). Reconciliation is left to a follow-up; the pcap is the
#    honest record that the proxy's fan-out count is a lower bound.
if command -v tcpdump >/dev/null 2>&1; then
  tcpdump -i any -w "${RUN_DIR}/backstop.pcap" -q 'tcp' >/dev/null 2>&1 &
  TCPDUMP_PID=$!
  trap 'kill "${MITM_PID}" "${TCPDUMP_PID}" 2>/dev/null || true' EXIT
fi

# 5. Drive every server through the proxy, sequentially.
python harness/drive_all.py --registry "${REGISTRY}" --run-dir "${RUN_DIR}" \
       --proxy "http://127.0.0.1:8080" --salt "${MCPFANOUT_SALT}"

# 6. Stop capture cleanly so the addon flushes flows.jsonl in its done() hook.
kill -TERM "${MITM_PID}" 2>/dev/null || true
wait "${MITM_PID}" 2>/dev/null || true
[[ -n "${TCPDUMP_PID:-}" ]] && kill "${TCPDUMP_PID}" 2>/dev/null || true

# 7. Compute the six numbers. Rule 6: this is the command behind the published figures.
python -m mcpfanout.cli aggregate --run "${RUN_DIR}" --number all | tee "${RUN_DIR}/numbers.json"
echo "[run] done: ${RUN_DIR}/numbers.json"
