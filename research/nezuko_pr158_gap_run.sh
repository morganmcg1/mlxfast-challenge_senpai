#!/usr/bin/env bash
# Research-only (PR #158): ABBA decode dead-time decomposition.
#
#   A = GPUPROF hook active   (DARKBLOOM_GPU_PROFILE=1, SPLIT=0)
#   B = same binary, hook off (env unset -> GpuDispatchProfiler::enabled_=false)
#
# A vs B isolates the profiler's own cost on `wall`, which decides whether the
# reported gap = wall - gpu_busy_union is measurable or self-inflicted. Each
# session also measures the request/response IPC floor with an unknown request
# kind so the gap can be split into IPC vs host-encode + GPU-idle.
#
# Requires the worker built from the profiler-patched device.cpp/device.h.
set -uo pipefail
cd "$(dirname "$0")/.."

STEPS="${STEPS:-200}"
PINGS="${PINGS:-400}"
OUT="${OUT:-research/nezuko-pr158-gap.log}"
: >"$OUT"

thermal() {
  "$HOME/bin/macmon" pipe -s1 2>/dev/null \
    | jq -c '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
    2>/dev/null || echo '{}'
}

run_one() {
  local arm="$1" tag="$2"
  echo "=== arm=$arm tag=$tag t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
  if [ "$arm" = "A" ]; then
    DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
      python3 research/nezuko_pr158_gap_probe.py \
      --steps "$STEPS" --pings "$PINGS" --profile --profile-top 44 \
      --label "$tag" --stderr "/tmp/nezuko-pr158-$tag.err" 2>&1 | tee -a "$OUT"
  else
    env -u DARKBLOOM_GPU_PROFILE -u DARKBLOOM_GPU_PROFILE_SPLIT \
      python3 research/nezuko_pr158_gap_probe.py \
      --steps "$STEPS" --pings "$PINGS" \
      --label "$tag" --stderr "/tmp/nezuko-pr158-$tag.err" 2>&1 | tee -a "$OUT"
  fi
  echo "=== arm=$arm tag=$tag done t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
}

SEQ="${SEQ:-A:a1 B:b1 B:b2 A:a2}"
for spec in $SEQ; do
  run_one "${spec%%:*}" "${spec##*:}"
done

echo "=== log -> $OUT"
grep -E "SUMMARY|per steady step|ipc_floor|divergences" "$OUT"
