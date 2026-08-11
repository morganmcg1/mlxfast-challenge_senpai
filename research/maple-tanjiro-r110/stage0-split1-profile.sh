#!/usr/bin/env bash
# R110-A rev4 Stage 0, second deliverable: kernel-level before/after for the
# norm+QKV fusion, plus the per-step dispatch count that disappears.
#
# Same three arms as stage0-norm-qkv-abba.sh, but under SPLIT=1 so each
# dispatch owns a command buffer and can be priced in isolation.  SPLIT=1 costs
# +1.554 us per command buffer (PR #685), so an arm with fewer dispatches is
# flattered by exactly 1.554 us x (dispatches removed) and that must be
# subtracted before the kernel tables are compared.  Under SPLIT=1 the count of
# command buffers inside the steady window divided by the number of steady
# steps IS the dispatch count per step, which is the number the fusion claim
# turns on.
#
# The GPUPROF hook is research-only instrumentation held in a patch file, not
# in the tree.  It touches device.cpp/device.h, which are not editable paths.
# This script applies it, builds, captures every arm from that one build, and
# reverts on every exit path, so no scored timing can ever run instrumented.
#
#   research/maple-tanjiro-r110/stage0-split1-profile.sh [OUT_DIR] [STEPS] [ARMS]
set -u
cd "$(dirname "$0")/../.."

OUT="${1:-/tmp/r110a-split1}"
STEPS="${2:-200}"
ARMS="${3:-FUN}"
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
  echo "build failed rc=${rc}"; tail -40 "${OUT}/build.log"; exit 3
fi

for (( n=0; n<${#ARMS}; n++ )); do
  arm="${ARMS:$n:1}"
  case "${arm}" in
    F) envargs=(DARKBLOOM_NATIVE_AFFINE_NVFP4=0) ;;
    U) envargs=(DARKBLOOM_NATIVE_AFFINE_NVFP4=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0) ;;
    N) envargs=() ;;
    *) echo "unknown arm ${arm}"; exit 2 ;;
  esac
  echo "=== SPLIT=1 capture arm ${arm}, ${STEPS} steps t=$(date -u +%H:%M:%S)"
  env ${envargs[@]+"${envargs[@]}"} DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py \
      --steps "${STEPS}" --profile --profile-top 60 \
      --stderr "${OUT}/${arm}.err" \
    > "${OUT}/${arm}.log" 2>&1
  echo "--- decode_probe rc=$? t=$(date -u +%H:%M:%S)"
  sed -n '/^profile:/,$p' "${OUT}/${arm}.log"
  grep -E 'teacher-forced|decode steps=' "${OUT}/${arm}.log"
  gzip -f "${OUT}/${arm}.err"
done

echo "=== done t=$(date -u +%H:%M:%S)"
