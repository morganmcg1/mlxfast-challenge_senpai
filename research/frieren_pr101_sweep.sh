#!/bin/bash
# Research-only: PR #101 gate_sp (R,NS) geometry sweep + o_proj hoist arm.
# Each point is a fresh worker process; profile mode attributes per-kernel GPU
# time so the ~3% gate_sp slice is measured directly instead of through the
# 34%-sigma wall clock.
set -u
cd "$(dirname "$0")/.."
OUT=research/pr101-sweep
mkdir -p "$OUT"
STEPS="${STEPS:-160}"

run_point() {
  local tag="$1"; shift
  local log="$OUT/$tag.txt"
  echo "=== $tag ($*) ==="
  env "$@" DARKBLOOM_GPU_PROFILE=1 \
    python3 research/decode_probe.py --steps "$STEPS" --profile --profile-top 44 \
      --stderr "$OUT/$tag.worker.err" >"$log" 2>&1
  echo "exit=$? $(grep -c . "$log") lines -> $log"
  grep -E 'divergence|^mean|gpu_busy_sum|gate_sp|oproj_act' "$log" | head -20
}

for R in 4 2 1; do
  for NS in 4 2 1; do
    run_point "gatesp_r${R}n${NS}" DARKBLOOM_GATESP_R="$R" DARKBLOOM_GATESP_NS="$NS"
  done
done

run_point "oproj_hoist_on" DARKBLOOM_OPROJ_LM_HOIST=1
run_point "oproj_hoist_off" DARKBLOOM_OPROJ_LM_HOIST=0
