#!/usr/bin/env bash
# R118-A closing sequence, run once after the ABBA campaign finishes.
#
#   1. correctness gate (Rule 105.15): the vendored-upstream equivalence oracle
#      at the DEFAULT arm, which is the shipped binary.  Must report a non-zero
#      exact-step count; zero selected tests is not a pass.
#   1b. divergence-cost addendum: paired per-step-index contrast of ship vs d1
#      split by whether the dose arm's token diverged, to price the routing
#      confound directly.  Needs the CLEAN worker, so it runs before step 2.
#   2. attribution: SPLIT=1 capture of ship / d1 / rd1 so tau can be measured
#      for this family instead of assumed.  Leaves an INSTRUMENTED worker.
#   3. rebuild the clean release worker so the branch is left rankable.
#
# Step 1 runs first and on the clean tree, so the correctness evidence is taken
# from exactly the source that is committed, with no research patch anywhere
# near it.
#
# Step 0 blocks until the ABBA campaign's worker processes are gone.  Only one
# model-holding process may run at a time on this host (~21 GB RSS each) and a
# second one would corrupt the campaign's timings, which are the primary result.
#
# Usage: finish-r118a.sh [stage]   stage in {part1, part2, all}; default all.
#   part1 = steps 0, 1a, 1b  (divergence cost, then equivalence; ~20 min)
#   part2 = steps 2, 3       (two builds, ~35 min)
# The split exists because the supervised-job wall clock killed the first
# campaign job at ~63 min; keeping each job well under an hour is cheap
# insurance.
set -u
cd "$(dirname "$0")/../.."
OUT="research/maple-tanjiro-r118/evidence"
mkdir -p "${OUT}"
STAGE="${1:-all}"

echo "############ 0. waiting for the ABBA campaign to release the GPU  t=$(date -u +%H:%M:%S)"
waited=0
while pgrep -f 'run-r118a.sh|resume-orderB.sh|mlxfast-runtime-worker' > /dev/null 2>&1; do
  sleep 20
  waited=$((waited + 20))
  if [ $((waited % 300)) -eq 0 ]; then
    echo "    still waiting, ${waited}s  t=$(date -u +%H:%M:%S)"
  fi
  if [ "${waited}" -gt 5400 ]; then
    echo "    gave up waiting after ${waited}s"; break
  fi
done
echo "############ campaign quiet after ${waited}s  t=$(date -u +%H:%M:%S)"
sleep 15

if [ "${STAGE}" = "all" ] || [ "${STAGE}" = "part1" ]; then

# 1a before 1b on purpose: 1a is a timing measurement and must run on a host in
# the same state the campaign left it in.  The equivalence oracle runs `swift
# test`, which compiles, and a compile is exactly the CPU-heavy work my own
# hygiene rule forbids next to a live timing run.  So the measurement goes first
# and the build goes after it.
echo "############ 1a. divergence-cost addendum (needs the CLEAN worker)  t=$(date -u +%H:%M:%S)"
bash research/maple-tanjiro-r118/divergence-cost.sh 160
echo "diverg rc=$?"

echo "############ 1b. equivalence oracle, default arm  t=$(date -u +%H:%M:%S)"
env -u DARKBLOOM_SHARED_QMV_ARM bash research/run_upstream_equivalence.sh \
  > "${OUT}/equivalence.log" 2>&1
echo "equivalence rc=$?"
grep -E 'EQUIVALENCE_EXACT_STEPS=|EQUIVALENCE_EXIT=|Test run with|error:' \
  "${OUT}/equivalence.log" | tail -20
echo "log bytes: $(wc -c < "${OUT}/equivalence.log")"

fi

if [ "${STAGE}" = "all" ] || [ "${STAGE}" = "part2" ]; then

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

fi
echo "############ done stage=${STAGE}  t=$(date -u +%H:%M:%S)"
