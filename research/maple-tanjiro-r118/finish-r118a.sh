#!/usr/bin/env bash
# R118-A closing sequence, run once after the ABBA campaign finishes.
#
#   1. correctness gate (Rule 105.15): the vendored-upstream equivalence oracle
#      at the DEFAULT arm, which is the shipped binary.  Must report a non-zero
#      exact-step count; zero selected tests is not a pass.
#   2. attribution: SPLIT=1 capture of ship / d1 / rd1 so tau can be measured
#      for this family instead of assumed.  Leaves an INSTRUMENTED worker.
#   3. rebuild the clean release worker so the branch is left rankable.
#
# Step 1 runs first and on the clean tree, so the correctness evidence is taken
# from exactly the source that is committed, with no research patch anywhere
# near it.
set -u
cd "$(dirname "$0")/../.."
OUT="research/maple-tanjiro-r118/evidence"
mkdir -p "${OUT}"

echo "############ 1. equivalence oracle, default arm  t=$(date -u +%H:%M:%S)"
env -u DARKBLOOM_SHARED_QMV_ARM bash research/run_upstream_equivalence.sh \
  > "${OUT}/equivalence.log" 2>&1
echo "equivalence rc=$?"
grep -E 'EQUIVALENCE_EXACT_STEPS=|EQUIVALENCE_EXIT=|Test run with|error:' \
  "${OUT}/equivalence.log" | tail -20
echo "log bytes: $(wc -c < "${OUT}/equivalence.log")"

echo "############ 2. SPLIT=1 attribution  t=$(date -u +%H:%M:%S)"
bash research/maple-tanjiro-r118/qmv-dose-profile.sh \
  "${OUT}/profile" 200 036630
echo "profile rc=$?"

echo "############ 3. rebuild clean release worker  t=$(date -u +%H:%M:%S)"
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    > "${OUT}/rebuild.log" 2>&1
echo "rebuild rc=$?"
git checkout -- Package.resolved 2>/dev/null
echo "############ git status of never-editable paths (must be empty):"
git status --porcelain -- \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h
echo "############ done  t=$(date -u +%H:%M:%S)"
