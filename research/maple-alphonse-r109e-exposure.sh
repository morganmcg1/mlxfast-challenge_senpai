#!/bin/bash
# Exposure of `full_fused_attn_grow_v1`: does GPU busy time removed from this
# kernel reach the step wall clock, or is it hidden behind a concurrent kernel?
#
#   research/maple-alphonse-r109e-exposure.sh [OUT_DIR] [STEPS]
#
# PR #685 comment 5246874781 asks for a nesting fraction. The PR-91 GPUPROF hook
# cannot supply one: at SPLIT=1 there is one dispatch per command buffer, so the
# timeline is serialised and nesting is 0% by construction, and at SPLIT=0 the
# hook emits one timestamp pair per command buffer, so overlap *inside* a
# command buffer is not observable at all. Both modes therefore report 0.00%
# nesting for structural reasons, not physical ones.
#
# This script answers the underlying question causally instead. The QK dose
# probe adds real in-kernel ALU work to `full_fused_attn_grow_v1` and nothing
# else. Running the same worker binary with the probe off and on gives
#
#   exposure = d(step wall) / d(global busy_sum)
#
# where both are measured by the same harness in the same session. Exposure ~ 1
# means busy time in this kernel is fully exposed to the wall clock and a busy
# saving converts one-for-one; exposure ~ 0 means it is hidden and no saving in
# this kernel can ever pay. SPLIT=0 is the honest configuration for the wall
# clock because it keeps MLX's real command-buffer batching. The two SPLIT=1
# captures are the attribution check: they confirm the busy delta lands in
# `full_fused_attn_grow_v1` and not somewhere else.
#
# Run order is a palindrome in the SPLIT=0 pair so a monotone session drift
# cancels out of the difference.
set -u
cd "$(dirname "$0")/.."

OUT="${1:-/tmp/r109e-exposure}"
STEPS="${2:-200}"
PATCH="research/pr91-gpuprof-hook.patch"
TOUCHED="Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h"

mkdir -p "${OUT}"

revert() {
  # shellcheck disable=SC2086
  git checkout -- ${TOUCHED}
  echo "=== reverted ${PATCH}; git status of touched files:"
  # shellcheck disable=SC2086
  git status --porcelain -- ${TOUCHED}
}
trap revert EXIT

echo "=== applying ${PATCH} t=$(date -u +%H:%M:%S)"
git apply "${PATCH}" || exit 2

echo "=== building instrumented worker t=$(date -u +%H:%M:%S)"
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    > "${OUT}/build.log" 2>&1
rc=$?
git checkout -- Package.resolved 2>/dev/null
if [ ${rc} -ne 0 ]; then
  echo "build failed rc=${rc}"
  tail -40 "${OUT}/build.log"
  exit 3
fi

# The probe mode is read from the environment and the kernel is JIT-compiled at
# warm-up, so one binary serves both arms and no rebuild sits between them.
capture() {
  local tag="$1" split="$2" probe="$3"
  echo "=== ${tag}: SPLIT=${split} probe='${probe}' t=$(date -u +%H:%M:%S)"
  env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="${split}" \
      DARKBLOOM_FULL_ATTN_QK_PROBE="${probe}" \
    python3 research/decode_probe.py \
      --steps "${STEPS}" --profile --profile-top 44 \
      --stderr "${OUT}/${tag}.err" \
    > "${OUT}/${tag}.log" 2>&1
  echo "--- rc=$?"
  grep -E 'divergences|^decode steps=|^per steady step:' "${OUT}/${tag}.log"
  grep -E 'full_fused_attn_grow_v1$' "${OUT}/${tag}.log" | head -4
  rm -f "${OUT}/${tag}.err"
}

capture s0_ctrl_a 0 ""
capture s0_dose_a 0 dose10
capture s0_dose_b 0 dose10
capture s0_ctrl_b 0 ""
capture s1_ctrl   1 ""
capture s1_dose   1 dose10

echo "=== summary t=$(date -u +%H:%M:%S)"
for f in s0_ctrl_a s0_dose_a s0_dose_b s0_ctrl_b s1_ctrl s1_dose; do
  printf '%-10s %s\n' "${f}" "$(grep -E '^per steady step:' "${OUT}/${f}.log")"
done
echo "=== full_fused_attn_grow_v1, SPLIT=1 only (isolated dispatch)"
for f in s1_ctrl s1_dose; do
  printf '%-10s %s\n' "${f}" \
    "$(grep -E 'full_fused_attn_grow_v1$' "${OUT}/${f}.log" | head -1)"
done
echo "=== done t=$(date -u +%H:%M:%S)"
