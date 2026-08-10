#!/bin/bash
# R105-C A2: one traced correctness run under the MLX dispatch-trace hook from
# research/r103b/scripts/trace.patch. The patch is applied, built into
# .build-worker, and reverted before this script runs, so the tracing lives only
# in the (gitignored) binary and never in a committed source file.
#
# Usage: fern_r105c_trace_arm.sh <arm-label> [VAR=VAL ...]
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARM="$1"; shift

DUMP="/tmp/r105c/dump/${ARM}"
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
STEP="${STEP:-5}"

cd "${ROOT}" || exit 3

env -i \
  HOME="${HOME:-/Users/ec2-user}" PATH="${PATH}" TMPDIR="${TMPDIR:-/tmp}" \
  USER="${USER:-ec2-user}" LOGNAME="${LOGNAME:-ec2-user}" SHELL=/bin/bash TERM=dumb \
  MLXFAST_NO_SANDBOX=1 \
  MLXFAST_RUNTIME_WORKER_EXECUTABLE="${WRAP}" \
  MLX_TRACE_DUMP_DIR="${DUMP}" \
  "$@" \
  "${CLI}" correctness-trace \
    --weights "${ROOT}/weights" \
    --golden "${ROOT}/correctness_prompts/public_longcopy_gate_english_512_256.json" \
    --step "${STEP}" \
    --top-k 5 \
  > "${DUMP}/trace_report.json" 2> "${DUMP}/cli_stderr.log"
RC=$?

NLIB=$(ls "${DUMP}"/lib_*.msl 2>/dev/null | wc -l | tr -d ' ')
NDISP=$( [ -f "${DUMP}/dispatch.tsv" ] && wc -l < "${DUMP}/dispatch.tsv" | tr -d ' ' || echo 0 )
echo "[${ARM}] rc=${RC} msl_libraries=${NLIB} dispatch_rows=${NDISP} env=$*"
echo "--- [${ARM}] cli_stderr tail ---"
tail -n 12 "${DUMP}/cli_stderr.log" 2>/dev/null
echo "--- [${ARM}] end ---"
exit 0
