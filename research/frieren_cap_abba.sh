#!/bin/bash
# Position-balanced ABBA re-measurement of the shipped command-buffer byte cap.
#
# Arms (both at ranked parity, DARKBLOOM_STARTUP_MEMORY_PROFILE=full):
#   A = shipped: no MLX_MAX_* in the environment, so
#       LagunaRuntimeWeights.swift:385-389 installs 200 MiB / 400 ops.
#   B = candidate: MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=400
#       (setenv overwrite=0 in-tree, so the explicit value wins; identical to
#       shipping 50/400 as the in-tree default).
#
# The unbalanced sweep that produced "cap 50 = 8.9579, n=5" ran its arms in
# blocks, and identical controls later measured 9.0356 / 9.1076 / 9.1136 across
# script positions (~0.8% saturating drift), which is larger than the 1.45%
# effect claimed. Three ABBA/BAAB blocks make each arm's positions sum to 39 and
# also balance within every block of four, so smooth drift cancels twice over:
#
#   pos:  1 2 3 4 | 5 6 7 8 | 9 10 11 12
#   arm:  A B B A | B A A B | A  B  B  A
#
# Position 0 is a discarded warm-up arm, because the earlier screen showed the
# coldest position is the outlier and the drift saturates rather than being
# linear.
set -u
cd "$(dirname "$0")/.."

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -3 || exit 1

MACMON="${HOME}/bin/macmon"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_temp:.temp.gpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
      2>/dev/null
  else
    echo "no-macmon"
  fi
}

run_arm() {
  local name="$1" arm="$2"
  echo "=== ${name} arm=${arm} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  if [ "${arm}" = "A" ]; then
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      python3 research/frieren_host_cpu_probe.py \
        --warmup-steps 60 --measure-steps 2000 --label "${name}-A" 2>/dev/null
  else
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=400 \
      python3 research/frieren_host_cpu_probe.py \
        --warmup-steps 60 --measure-steps 2000 --label "${name}-B" 2>/dev/null
  fi
}

run_arm p00-discard A
run_arm p01 A
run_arm p02 B
run_arm p03 B
run_arm p04 A
run_arm p05 B
run_arm p06 A
run_arm p07 A
run_arm p08 B
run_arm p09 A
run_arm p10 B
run_arm p11 B
run_arm p12 A
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
