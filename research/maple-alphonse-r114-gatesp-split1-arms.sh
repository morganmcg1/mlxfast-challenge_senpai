#!/bin/bash
# R114-E Stage 3.5: SPLIT=1 busy attribution for BOTH arms of the gate_sp
# grid-append fusion, from a single instrumented build.
#
#   research/maple-alphonse-r114-gatesp-split1-arms.sh [OUT_DIR] [STEPS]
#
# SPLIT=1 gives one dispatch per command buffer, so a busy record finally
# names a kernel instead of a command buffer.  It is attribution only:
# feedback r116-e records that SPLIT=1 inflates wall by +19.6 % and mis-ranks
# arms, so the ranking number for this experiment comes from the SPLIT=0
# paired ABBA, never from here.
#
# The two arms differ only by DARKBLOOM_DECODE_QKV_GATE_FUSED, read once per
# worker process, so one build serves both and the comparison cannot be
# confounded by a rebuild.
#
# The GPUPROF hook is research-only instrumentation held in a patch file.  It
# is applied here and reverted on every exit path, so no timing that counts
# can run against an instrumented build.
set -u
cd "$(dirname "$0")/.."

OUT="${1:-/tmp/r114-split1-arms}"
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

capture() {
  arm="$1"; shift
  echo "=== arm ${arm}: SPLIT=1 capture, ${STEPS} steps t=$(date -u +%H:%M:%S)"
  env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 "$@" \
    python3 research/decode_probe.py \
      --steps "${STEPS}" --profile --profile-top 44 \
      --stderr "${OUT}/${arm}.err" \
    > "${OUT}/${arm}.log" 2>&1
  echo "--- decode_probe rc=$? t=$(date -u +%H:%M:%S)"
  tail -50 "${OUT}/${arm}.log"

  echo "=== arm ${arm}: per-kernel nesting"
  python3 research/maple-alphonse-r109e-nesting.py "${OUT}/${arm}.err" \
    laguna_gate_sp laguna_decode_nvfp4_qkv \
    | tee "${OUT}/${arm}-nesting.txt"
  gzip -f "${OUT}/${arm}.err"
}

# C first, then F, then C again: the repeat prices the drift between the two
# captures on the arm that is supposed to be unchanged.
capture C1 DARKBLOOM_DECODE_QKV_GATE_FUSED=0
capture F1
capture C2 DARKBLOOM_DECODE_QKV_GATE_FUSED=0

echo "=== done t=$(date -u +%H:%M:%S)"
