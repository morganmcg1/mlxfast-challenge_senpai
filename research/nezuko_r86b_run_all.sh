#!/usr/bin/env bash
# Research-only R86-B driver: ABBA ladder followed by the CP-1 size sweep.
#
#   research/nezuko_r86b_run_all.sh /tmp/r86b [LADDER_BLOCKS] [SIZE_BLOCKS] [STEPS]
#
# One job so the two sweeps never contend for the model-holding worker.
set -uo pipefail
ROOT="${1:?root outdir}"
LB="${2:-1}"
SB="${3:-1}"
STEPS="${4:-200}"
here="$(cd "$(dirname "$0")" && pwd)"

echo "=== $(date -u +%H:%M:%S) ladder blocks=${LB} steps=${STEPS}"
bash "${here}/nezuko_r86b_ladder.sh" "${ROOT}/ladder" "${LB}" "${STEPS}"
echo "=== $(date -u +%H:%M:%S) size blocks=${SB} steps=${STEPS}"
bash "${here}/nezuko_r86b_size.sh" "${ROOT}/size" "${SB}" "${STEPS}"
echo "=== $(date -u +%H:%M:%S) all done"
