#!/usr/bin/env bash
# R97-B: route table + kernel-time census for DARKBLOOM_FUSED_QKV off/on.
# Trace and profile are run in separate processes because each perturbs timing.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=research/r97-logs
mkdir -p "${OUT}"
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full

for TAG in off on; do
  if [ "${TAG}" = "on" ]; then export DARKBLOOM_FUSED_QKV=1; else export DARKBLOOM_FUSED_QKV=0; fi

  DARKBLOOM_STEEL_TRACE=1 python3 research/prefill_probe.py --reps 2 \
    --stderr "${OUT}/steeltrace.${TAG}.err" >"${OUT}/steeltrace.${TAG}.log" 2>&1
  echo "trace ${TAG}: exit=$? lines=$(grep -c 'darkbloom\]\[steel' "${OUT}/steeltrace.${TAG}.err" || true)"

  python3 research/prefill_probe.py --reps 3 --profile --profile-top 40 \
    --stderr "${OUT}/profile.${TAG}.err" >"${OUT}/profile.${TAG}.log" 2>&1
  echo "profile ${TAG}: exit=$?"
done
