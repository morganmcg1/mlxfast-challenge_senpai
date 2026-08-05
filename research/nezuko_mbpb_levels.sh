#!/bin/bash
# Deliverable B: mirrored position-balanced dose-response for
# MLX_MAX_MB_PER_BUFFER over {12, 25, 50, 100, 200} with
# MLX_MAX_OPS_PER_BUFFER pinned at 200 (the shipped ops cap).
#
# Every arm runs at ranked parity (DARKBLOOM_STARTUP_MEMORY_PROFILE=full) in a
# fresh worker process. In-tree setenv uses overwrite=0, so the explicit
# environment value wins and one binary can serve every level.
#
# Phase 1 (verdict): wall ms/step from frieren_host_cpu_probe.py.
#   Four mirrored blocks, so each level's positions sum to 11 within the first
#   mirrored pair and 31 within the second. Smooth thermal/allocator drift
#   cancels within each pair, and each level gets n=4 for a paired t-test on
#   within-block differences against 200 MB.
#
#     pos:   1   2  3  4   5 |  6   7  8  9   10 | 11  12 13 14  15 | 16  17 18 19  20
#     level: 200 12 25 50 100| 100 50 25 12 200  | 200 12 25 50 100| 100 50 25 12 200
#
#   Position 0 is a discarded warm-up arm: the coldest position is the outlier
#   and the drift saturates rather than being linear.
#
# Phase 2 (diagnostics only): one profiled decode_probe pass per level for
# cb/step, GPU busy union, and host gap. Union shrinks mechanically as the
# command-buffer count rises, so it explains but never overrules phase 1.
set -u
cd "$(dirname "$0")/.."

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -3 || exit 1

MACMON="${HOME}/bin/macmon"
MEASURE_STEPS="${MEASURE_STEPS:-2000}"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
      2>/dev/null
  else
    echo "no-macmon"
  fi
}

wall_arm() {
  local name="$1" mb="$2"
  echo "=== ${name} mb=${mb} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=200 \
    python3 research/frieren_host_cpu_probe.py \
      --warmup-steps 60 --measure-steps "${MEASURE_STEPS}" \
      --label "${name}-mb${mb}" 2>/dev/null
}

profile_arm() {
  local mb="$1"
  echo "=== profile mb=${mb} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=200 \
      DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
    python3 research/decode_probe.py --steps 200 --profile --profile-top 6 \
      2>/dev/null | grep -E "per steady step|profile:|divergence"
}

wall_arm p00-discard 200

i=0
for level in 200 12 25 50 100  100 50 25 12 200  200 12 25 50 100  100 50 25 12 200; do
  i=$((i + 1))
  wall_arm "$(printf 'p%02d' "${i}")" "${level}"
done

echo "=== phase1 done t=$(date -u +%H:%M:%S) thermal=$(thermal)"

for level in 200 12 25 50 100; do
  profile_arm "${level}"
done

echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
