#!/bin/bash
# R106-C: capture one decode dispatch trace with buffer ranges, barrier flags
# and encoder ids, using the worker built from research/r106c/scripts/trace_dag.patch.
# Usage: run_dag_trace.sh <arm-label> [STEP]
set -u

ROOT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-fern/workspace/target"
ARM="${1:-dag}"
STEP="${2:-5}"

DUMP="/tmp/r106c/dump/${ARM}"
rm -rf "${DUMP}"; mkdir -p "${DUMP}"

REALWORKER="${ROOT}/.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker"
if [ ! -x "${REALWORKER}" ]; then
  echo "[${ARM}] MISSING worker ${REALWORKER}" >&2
  exit 2
fi

WRAP="${DUMP}/worker-wrap.sh"
cat > "${WRAP}" <<EOF
#!/bin/bash
exec "${REALWORKER}" "\$@" 2>> "${DUMP}/worker_stderr.log"
EOF
chmod +x "${WRAP}"

CLI="${ROOT}/.build/release/mlxfast-swift"
cd "${ROOT}" || exit 3

env -i \
  HOME="${HOME:-/Users/ec2-user}" PATH="${PATH}" TMPDIR="${TMPDIR:-/tmp}" \
  USER="${USER:-ec2-user}" LOGNAME="${LOGNAME:-ec2-user}" SHELL=/bin/bash TERM=dumb \
  MLXFAST_NO_SANDBOX=1 \
  MLXFAST_RUNTIME_WORKER_EXECUTABLE="${WRAP}" \
  MLX_TRACE_DUMP_DIR="${DUMP}" \
  "${CLI}" correctness-trace \
    --weights "${ROOT}/weights" \
    --golden "${ROOT}/correctness_prompts/public_longcopy_gate_english_512_256.json" \
    --step "${STEP}" \
    --top-k 5 \
  > "${DUMP}/trace_report.json" 2> "${DUMP}/cli_stderr.log"
RC=$?

NDISP=$( [ -f "${DUMP}/dispatch.tsv" ] && wc -l < "${DUMP}/dispatch.tsv" | tr -d ' ' || echo 0 )
echo "[${ARM}] rc=${RC} dispatch_rows=${NDISP} dump=${DUMP}"
echo "--- cli_stderr tail ---"; tail -n 15 "${DUMP}/cli_stderr.log" 2>/dev/null
echo "--- worker_stderr tail ---"; tail -n 15 "${DUMP}/worker_stderr.log" 2>/dev/null
echo "--- report head ---"; head -c 400 "${DUMP}/trace_report.json" 2>/dev/null; echo
exit "${RC}"
