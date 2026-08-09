#!/usr/bin/env bash
# R97-B: per-kernel dispatch/time census for DARKBLOOM_FUSED_QKV off/on.
# Diagnostic only: the GPUPROF hook perturbs the wall clock, so read dispatch
# counts and per-kernel shares from here, never a headline timing claim.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=research/r97-logs
mkdir -p "${OUT}"

for TAG in off on; do
  if [ "${TAG}" = "on" ]; then export DARKBLOOM_FUSED_QKV=1; else export DARKBLOOM_FUSED_QKV=0; fi

  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/prefill_probe.py --reps 3 --profile --profile-top 40 \
    --stderr "${OUT}/profile.${TAG}.err" >"${OUT}/profile.${TAG}.log" 2>&1
  echo "profile ${TAG}: exit=$?"
done
