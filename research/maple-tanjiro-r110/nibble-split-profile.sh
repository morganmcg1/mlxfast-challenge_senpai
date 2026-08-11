#!/usr/bin/env bash
# R116-B step 5: per-kernel attribution for DARKBLOOM_NVFP4_NIBBLE_SPLIT.
#
# ATTRIBUTION ONLY.  DARKBLOOM_GPU_PROFILE_SPLIT=1 inflates wall by +19.6 % on
# this host and MIS-RANKS arms, so nothing produced here may be quoted as a
# ranking.  The ranking lives in nibble-split-abba.sh / abba.tsv.
#
# Question this answers: the ABBA contrast is a whole-process number.  Does the
# arm difference actually land on the NVFP4 QMV family (the 16 registrations of
# lagunaSharedSwiGLUQMVHeader), or somewhere else?  Arm 0 and arm 2 compile to a
# byte-identical metallib (nibble-split-isa.sh), so their per-kernel rows are a
# negative control for the profiler itself.
#
# The GPUPROF hook is research-only instrumentation held in a patch file, not in
# the tree; it touches device.cpp/device.h, which are NOT editable paths.  This
# script applies it, builds one instrumented worker, captures every arm from
# that build, and reverts on every exit path.  It leaves an instrumented binary
# in .build-worker, so any ranking run afterwards must rebuild first
# (nibble-split-abba.sh does).
#
# Order 012210 is a palindrome: each arm's two reps are symmetric about the
# session midpoint, so linear drift cancels within each arm's mean.  Every arm
# is set explicitly, including the default 1, so no arm is the odd one taking
# the env-parse `else` branch.
#
#   research/maple-tanjiro-r110/nibble-split-profile.sh [OUT_DIR] [STEPS] [ORDER]
set -u
cd "$(dirname "$0")/../.."

OUT="${1:-/tmp/r116b-prof}"
STEPS="${2:-200}"
ORDER="${3:-012210}"
PATCH="research/pr91-gpuprof-hook.patch"
TOUCHED="Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h"

mkdir -p "${OUT}"

if ! git diff --quiet -- Sources/MLXFastModel/LagunaRuntimeModel.swift; then
  echo "REFUSING: LagunaRuntimeModel.swift is dirty"
  exit 4
fi

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

for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((n+1))
  case "${arm}" in
    0|1|2) : ;;
    *) echo "unknown arm ${arm}"; exit 2 ;;
  esac
  tag="p${i}_${arm}"
  echo "=== SPLIT=1 capture ${tag}, ${STEPS} steps t=$(date -u +%H:%M:%S)"
  env DARKBLOOM_NVFP4_NIBBLE_SPLIT="${arm}" \
      DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py \
      --steps "${STEPS}" --profile --profile-top 60 \
      --stderr "${OUT}/${tag}.err" \
    > "${OUT}/${tag}.log" 2>&1
  echo "--- decode_probe rc=$? t=$(date -u +%H:%M:%S)"
  sed -n '/^profile:/,$p' "${OUT}/${tag}.log"
  grep -E 'teacher-forced|decode steps=' "${OUT}/${tag}.log"
  rm -f "${OUT}/${tag}.err"
done

echo "=== done t=$(date -u +%H:%M:%S)"
