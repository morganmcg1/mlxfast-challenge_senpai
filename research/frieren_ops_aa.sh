#!/bin/bash
# Position-balanced A/A screen on the MLX_MAX_OPS_PER_BUFFER axis.
#
#   A = MLX_MAX_MB_PER_BUFFER=200 MLX_MAX_OPS_PER_BUFFER=200  (shipped pair)
#   B = MLX_MAX_MB_PER_BUFFER=200 MLX_MAX_OPS_PER_BUFFER=400  (the reverted value)
#
# research/frieren_cb_binding_sweep.sh proved these two produce the *same*
# command-buffer partition: 50.0 cb/step, identical ops-per-cb histograms, and
# zero command buffers anywhere near the op limit (max observed 28 of 200). So
# this contrast is an A/A by construction and any measured delta is this
# harness's noise floor at 2000 steps/arm over 12 balanced positions. It serves
# two purposes: it closes the ops axis in the metric currency (T, not cb/step),
# and it calibrates every other contrast measured with the same design.
#
# Same balanced layout as research/frieren_cap_abba.sh: positions sum to 39 per
# arm and balance within each block of four, so smooth drift cancels twice.
#
#   pos:  1 2 3 4 | 5 6 7 8 | 9 10 11 12
#   arm:  A B B A | B A A B | A  B  B  A
set -u
cd "$(dirname "$0")/.."

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -3 || exit 1
git checkout -- Package.resolved

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
  local name="$1" arm="$2" ops
  if [ "${arm}" = "A" ]; then ops=200; else ops=400; fi
  echo "=== ${name} arm=${arm} ops=${ops} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      MLX_MAX_MB_PER_BUFFER=200 MLX_MAX_OPS_PER_BUFFER="${ops}" \
    python3 research/frieren_host_cpu_probe.py \
      --warmup-steps 60 --measure-steps 2000 --label "${name}-${arm}" 2>/dev/null
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
