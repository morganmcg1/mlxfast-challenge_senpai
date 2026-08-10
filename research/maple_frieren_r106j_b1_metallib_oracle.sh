#!/bin/bash
# R106-J / Deliverable B, stage B1 (second attempt).
#
# The first attempt (research/maple_frieren_r106j_b1_rerun.sh) force-cleaned
# .build-worker and rebuilt only `--product mlxfast-runtime-worker`. That
# earned the force-clean build receipt honestly, but it also deleted the
# CMake/Metal artifact mlx.metallib -- which is NOT in SwiftPM's build graph,
# so `swift build` can never regenerate it. Consequence: the upstream
# equivalence oracle aborted at first GPU use ("Failed to load the default
# metallib"), its metallib-seeding retry could not fire because the seed file
# was the very thing that had been deleted, and the script exited 3 with zero
# selected tests. Zero selected tests is not a pass, so that row is unearned.
#
# This script closes that gap in the only correct order:
#   1. rebuild mlx.metallib from the vendored Metal sources (tools/build-mlx-metallib.sh)
#   2. re-run research/run_upstream_equivalence.sh, which can now seed the
#      test bundle from a real metallib and retry
# and records enough of a receipt that a reader can tell which claim came from
# which stage. It deliberately does not touch the worker binary: the binary
# under test is the force-clean one from attempt 1
# (sha256 f2c3a889..., 49,096,008 bytes), and rebuilding it would invalidate
# that receipt.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
OUT="${1:-/tmp/r106j-b1b}"
mkdir -p "${OUT}"

WORKER=".build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker"
METALLIB=".build-worker/arm64-apple-macosx/release/mlx.metallib"

echo "R106J_B1B_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "R106J_B1B_HEAD=$(git rev-parse HEAD)"
echo "R106J_B1B_DIRTY=$(git status --porcelain | wc -l | tr -d ' ')"

# --- provenance of the binary we are about to certify -----------------------
if [ -f "${WORKER}" ]; then
  echo "WORKER_SHA256=$(shasum -a 256 "${WORKER}" | awk '{print $1}')"
  echo "WORKER_BYTES=$(stat -f %z "${WORKER}")"
else
  echo "WORKER_SHA256=MISSING"
fi
echo "METALLIB_PRESENT_BEFORE=$([ -f "${METALLIB}" ] && echo yes || echo no)"

# --- stage 1: rebuild the metallib -----------------------------------------
echo "=== STAGE 1: tools/build-mlx-metallib.sh ==="
t0=$(date +%s)
tools/build-mlx-metallib.sh >"${OUT}/metallib.log" 2>"${OUT}/metallib.err"
METALLIB_EXIT=$?
t1=$(date +%s)
echo "METALLIB_EXIT=${METALLIB_EXIT}"
echo "METALLIB_SECONDS=$((t1 - t0))"
tail -5 "${OUT}/metallib.err" | sed 's/^/METALLIB_ERR_TAIL: /'
tail -5 "${OUT}/metallib.log" | sed 's/^/METALLIB_LOG_TAIL: /'

if [ -f "${METALLIB}" ]; then
  echo "METALLIB_PRESENT_AFTER=yes"
  echo "METALLIB_SHA256=$(shasum -a 256 "${METALLIB}" | awk '{print $1}')"
  echo "METALLIB_BYTES=$(stat -f %z "${METALLIB}")"
else
  echo "METALLIB_PRESENT_AFTER=no"
fi

if [ "${METALLIB_EXIT}" -ne 0 ]; then
  echo "R106J_B1B_RESULT=METALLIB_BUILD_FAILED"
  echo "R106J_B1B_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 10
fi

# --- stage 2: the upstream equivalence oracle -------------------------------
echo "=== STAGE 2: research/run_upstream_equivalence.sh ==="
t0=$(date +%s)
research/run_upstream_equivalence.sh >"${OUT}/equivalence.log" 2>&1
EQ_EXIT=$?
t1=$(date +%s)
echo "EQUIVALENCE_SCRIPT_EXIT=${EQ_EXIT}"
echo "EQUIVALENCE_SECONDS=$((t1 - t0))"
grep -E '^EQUIVALENCE_(EXACT_STEPS|EXIT)=' "${OUT}/equivalence.log" \
  | sed 's/^/EQ_/' || true
echo "EQ_REPORT_MARKERS=$(grep -c '"promptTokenCount"' "${OUT}/equivalence.log")"
echo "EQ_ZERO_ERROR_STEPS=$(grep -c '"maximumAbsoluteLogitError" : 0,' "${OUT}/equivalence.log")"
echo "EQ_NONZERO_ERROR_LINES=$(grep '"maximumAbsoluteLogitError"' "${OUT}/equivalence.log" | grep -cv ' : 0,')"
grep -E 'Test run with|Executed [0-9]+ test|error:|failed' "${OUT}/equivalence.log" \
  | tail -12 | sed 's/^/EQ_TAIL: /'

if [ "${EQ_EXIT}" -eq 0 ]; then
  echo "R106J_B1B_RESULT=ORACLE_GREEN"
else
  echo "R106J_B1B_RESULT=ORACLE_NOT_GREEN_EXIT_${EQ_EXIT}"
fi
echo "R106J_B1B_END=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "${EQ_EXIT}"
