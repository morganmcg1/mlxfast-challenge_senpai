#!/usr/bin/env bash
# Research-only (PR #158): command-buffer split sweep.
#
# GPUPROF emits one record per committed MTLCommandBuffer, so at the shipped
# batching policy (SPLIT=0, ~9 dispatches per buffer) `gpu_busy_union` cannot
# see anything that happens *inside* a buffer -- neither intra-buffer idle nor
# intra-buffer concurrency. MLX opens encoders DispatchTypeConcurrent and only
# barriers on a real RAW/WAR hazard (device.cpp:548, :318-375), so overlap is
# possible in principle.
#
# DARKBLOOM_GPU_PROFILE_SPLIT=k caps dispatches per buffer at k, which both
# raises the record count and forces serialization at every boundary. Sweeping
# k gives sum(CB spans) as a function of buffers/step. If the shipped policy
# overlapped work, the SPLIT=0 union would sit well below the k-sweep line
# extrapolated to its buffer count; if it sits on the line, decode is already
# fully exposed and isolated per-dispatch durations are honest.
set -uo pipefail
cd "$(dirname "$0")/.."

STEPS="${STEPS:-200}"
PINGS="${PINGS:-20}"
OUT="${OUT:-research/nezuko-pr158-split-sweep.log}"
: >"$OUT"

thermal() {
  "$HOME/bin/macmon" pipe -s1 2>/dev/null \
    | jq -c '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
    2>/dev/null || echo '{}'
}

for k in ${SPLITS:-0 1 2 4 8 0}; do
  tag="split$k-$(date +%H%M%S)"
  echo "=== split=$k tag=$tag t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="$k" \
    python3 research/nezuko_pr158_gap_probe.py \
    --steps "$STEPS" --pings "$PINGS" --profile --profile-top 12 \
    --label "$tag" --stderr "/tmp/nezuko-pr158-$tag.err" 2>&1 | tee -a "$OUT"
  echo "=== split=$k done t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
done

echo "=== log -> $OUT"
grep -E "^=== split|SUMMARY|per steady step|divergences" "$OUT"
