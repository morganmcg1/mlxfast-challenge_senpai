#!/bin/bash
# One SPLIT=1 decode profile, to answer the question PR #685 comment 5246874781
# asks of my arm: what fraction of `full_fused_attn_grow_v1`'s GPU busy time is
# already hidden behind a concurrent kernel? Any busy saving in a nested kernel
# does not reach the step wall clock.
#
#   research/maple-alphonse-r109e-split1-profile.sh [OUT_DIR] [STEPS]
#
# The GPUPROF hook is research-only instrumentation that lives in a patch file,
# not in the tree. This script applies it, builds the worker the way
# benchmark.sh does, takes the capture, and reverts the patch on every exit
# path, so no timing that counts can ever run against an instrumented build.
set -u
cd "$(dirname "$0")/.."

OUT="${1:-/tmp/r109e-split1}"
STEPS="${2:-200}"
# SPLIT=1 isolates one dispatch per command buffer, which serialises the
# timeline and therefore reports 0% nesting by construction; it prices each
# kernel in isolation. SPLIT=0 keeps MLX's real batching, so overlap is
# observable but only the command buffers that happen to hold a single
# dispatch can be attributed to one kernel. Both captures are needed to say
# how much of a kernel's busy time is hidden.
SPLIT="${3:-1}"
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

echo "=== SPLIT=${SPLIT} capture, ${STEPS} steps t=$(date -u +%H:%M:%S)"
env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="${SPLIT}" \
  python3 research/decode_probe.py \
    --steps "${STEPS}" --profile --profile-top 44 \
    --stderr "${OUT}/split${SPLIT}.err" \
  > "${OUT}/split${SPLIT}.log" 2>&1
echo "--- decode_probe rc=$? t=$(date -u +%H:%M:%S)"
tail -60 "${OUT}/split${SPLIT}.log"

echo "=== per-kernel nesting"
python3 research/maple-alphonse-r109e-nesting.py "${OUT}/split${SPLIT}.err" \
  full_fused_attn_grow sliding_fused_attn_ring laguna_gate_sp routed_swiglu \
  residual_rms_router oproj_act down_residual \
  | tee "${OUT}/nesting.txt"

gzip -f "${OUT}/split${SPLIT}.err"
echo "=== done t=$(date -u +%H:%M:%S)"
