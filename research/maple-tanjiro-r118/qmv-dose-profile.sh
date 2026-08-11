#!/usr/bin/env bash
# R118-A step 5: measure tau for the gate+up QMV family, in situ, directly.
#
# ATTRIBUTION ONLY.  DARKBLOOM_GPU_PROFILE_SPLIT=1 inflates wall by ~+19.6 % on
# this host and MIS-RANKS arms.  Nothing produced here may be quoted as a
# ranking; the ranking lives in evidence/order{A,B}/abba.tsv.
#
# What this is for.  The dose arms remove a known number of device bytes from
# one kernel and the ABBA campaign measures the resulting change in DECODE WALL.
# That wall number needs no tau correction - it is already wall.  What it does
# not tell you is how much GPU BUSY time the same dose removed, and therefore
# what the busy-to-wall conversion factor tau actually is for this kernel
# family.  My standing law L-PROFILED-BUSY-OVERPREDICTS-WALL-2X puts tau at
# 0.54 with CI [0.29, 0.79] campaign-wide; cedar's #699 puts it at [0.27, 0.43].
# Both were fitted across heterogeneous edits.  Here I get it for one family
# from one binary:
#
#     tau(family) = delta(wall, SPLIT=0 campaign) / delta(busy, SPLIT=1 here)
#
# and the delta(busy) side is read off the profiler's own per-kernel row for the
# kernel that was dosed, which is as close to a clean causal handle as this
# machine offers.
#
# The GPUPROF hook is research-only instrumentation held in a patch file, not in
# the tree; it touches device.cpp/device.h, which are NOT editable paths.  This
# script applies it, builds one instrumented worker, captures every arm from
# that build, and reverts on every exit path.  It leaves an INSTRUMENTED binary
# in .build-worker, so any ranking or correctness run afterwards must rebuild.
#
# Order 036630 is a palindrome: each arm's two reps are symmetric about the
# session midpoint, so linear drift cancels within each arm's mean.
#   0 = ship (both kernels untouched, byte-identical to the shipped binary)
#   3 = d1   (shared gate+up QMV reads 1 of 4 K blocks; -32.6 MB/step)
#   6 = rd1  (routed gate+up QMV reads 1 of 4 K blocks; -260.7 MB/step)
#
#   research/maple-tanjiro-r118/qmv-dose-profile.sh [OUT_DIR] [STEPS] [ORDER]
set -u
cd "$(dirname "$0")/../.."

OUT="${1:-research/maple-tanjiro-r118/evidence/profile}"
STEPS="${2:-200}"
ORDER="${3:-036630}"
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
  d="${ORDER:$n:1}"
  i=$((n+1))
  case "${d}" in
    0) arm=ship ;;
    3) arm=d1 ;;
    6) arm=rd1 ;;
    *) echo "unknown digit ${d}"; exit 2 ;;
  esac
  tag="p${i}_${arm}"
  echo "=== SPLIT=1 capture ${tag} (arm ${arm}), ${STEPS} steps t=$(date -u +%H:%M:%S)"
  env DARKBLOOM_SHARED_QMV_ARM="${arm}" \
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
