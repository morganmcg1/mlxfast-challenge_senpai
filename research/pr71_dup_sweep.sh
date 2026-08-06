#!/usr/bin/env bash
# PR #71 Step 0: in-situ additive duplication sweep for the routed gate/up
# NVFP4 QMV decode kernel (research instrument, not a submitted path).
#
# Each arm runs one matched ./benchmark.sh --local-iterate with
# DARKBLOOM_ROUTED_QMV_DUP=N and files the sealed score JSON under
# research/pr71-dup/. The marginal per-dispatch decode cost is the OLS slope of
# decode_seconds_per_token against N.
set -uo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="research/pr71-dup"
mkdir -p "${OUT_DIR}"

for n in "$@"; do
  echo "=== DARKBLOOM_ROUTED_QMV_DUP=${n} ==="
  DARKBLOOM_ROUTED_QMV_DUP="${n}" ./benchmark.sh --local-iterate
  status=$?
  if [[ ${status} -ne 0 ]]; then
    echo "arm N=${n} failed with status ${status}"
    exit "${status}"
  fi
  cp score.local-iterate.json "${OUT_DIR}/score.dup${n}.json"
  echo "--- filed ${OUT_DIR}/score.dup${n}.json ---"
done

echo "=== sweep summary ==="
for f in "${OUT_DIR}"/score.dup*.json; do
  echo "${f}"
  grep -E '"(decode_seconds_per_token|prefill_seconds_per_token|passed_correctness|max_abs_diff|golden_hash)"' "${f}"
done
