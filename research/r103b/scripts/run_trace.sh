#!/bin/bash
# Usage: run_trace.sh <worktree-name> <arm-label> [env assignments...]
# Runs one correctness-trace under the MSL/dispatch tracing hook.
set -u

ROOT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-tanjiro/workspace/target"
WT="$1"; shift
ARM="$1"; shift

WTDIR="${ROOT}/.mlxfast-private/${WT}"
DUMP="/tmp/r103b/dump/${ARM}"
rm -rf "${DUMP}"; mkdir -p "${DUMP}"

REALWORKER="${WTDIR}/.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker"
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

cd "${WTDIR}" || exit 3

env -i \
  HOME="${HOME:-/Users/ec2-user}" PATH="${PATH}" TMPDIR="${TMPDIR:-/tmp}" \
  USER="${USER:-ec2-user}" LOGNAME="${LOGNAME:-ec2-user}" SHELL=/bin/bash TERM=dumb \
  MLXFAST_NO_SANDBOX=1 \
  MLXFAST_RUNTIME_WORKER_EXECUTABLE="${WRAP}" \
  MLX_TRACE_DUMP_DIR="${DUMP}" \
  DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
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
echo "[${ARM}] rc=${RC} msl_libraries=${NLIB} dispatch_rows=${NDISP}"
echo "--- [${ARM}] cli_stderr tail ---"
tail -n 25 "${DUMP}/cli_stderr.log" 2>/dev/null
echo "--- [${ARM}] worker_stderr tail ---"
tail -n 40 "${DUMP}/worker_stderr.log" 2>/dev/null
echo "--- [${ARM}] end ---"
exit 0
