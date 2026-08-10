#!/bin/bash
# R106-J / Deliverable B1 re-run, honestly this time.
#
# Two things the B1 table claimed and that I had not actually done in this
# session: (a) a force-clean release build of the scored worker product, and
# (b) research/run_upstream_equivalence.sh. This script does both, in that
# order, and leaves every transcript on disk so the table can cite a file
# rather than a memory.
#
# Deliberately NOT parameterised: there is exactly one honest way to run it.
set -u
cd "$(dirname "$0")/.." || exit 1

OUT=/tmp/r106j-b1
mkdir -p "${OUT}"

export CLANG_MODULE_CACHE_PATH="${OUT}/modulecache"

echo "=== R106-J B1 re-run, started $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "HEAD: $(git rev-parse HEAD)"
echo "worktree dirty files: $(git status --porcelain | wc -l | tr -d ' ')"

# ---------------------------------------------------------------- force clean
# "Force-clean" means the scratch path is destroyed, not that swift is asked
# nicely to rebuild. Anything less leaves object files whose provenance I
# cannot state.
echo
echo "--- stage 1: destroying .build-worker ---"
BEFORE_OBJ=$(find .build-worker -name '*.o' 2>/dev/null | wc -l | tr -d ' ')
echo "object files before: ${BEFORE_OBJ}"
rm -rf .build-worker
echo "removed: $([ -d .build-worker ] && echo NO || echo YES)"

echo
echo "--- stage 2: force-clean release build of mlxfast-runtime-worker ---"
BUILD_T0=$(date +%s)
swift build -c release --force-resolved-versions \
    --scratch-path .build-worker \
    --product mlxfast-runtime-worker \
    > "${OUT}/build.log" 2> "${OUT}/build.err"
BUILD_STATUS=$?
BUILD_T1=$(date +%s)
echo "BUILD_EXIT=${BUILD_STATUS}"
echo "BUILD_SECONDS=$((BUILD_T1 - BUILD_T0))"
AFTER_OBJ=$(find .build-worker -name '*.o' 2>/dev/null | wc -l | tr -d ' ')
echo "object files after: ${AFTER_OBJ}"
# Every object must postdate the rm. If any predates it the build was not clean.
STALE=$(find .build-worker -name '*.o' ! -newermt "@${BUILD_T0}" 2>/dev/null | wc -l | tr -d ' ')
echo "OBJECTS_PREDATING_CLEAN=${STALE}"
if [ -f .build-worker/release/mlxfast-runtime-worker ]; then
    echo "WORKER_SHA256=$(shasum -a 256 .build-worker/release/mlxfast-runtime-worker | cut -d' ' -f1)"
    echo "WORKER_BYTES=$(stat -f%z .build-worker/release/mlxfast-runtime-worker)"
else
    echo "WORKER_SHA256=MISSING"
fi
echo "--- tail of build.err ---"
tail -n 25 "${OUT}/build.err"

if [ "${BUILD_STATUS}" -ne 0 ]; then
    echo "=== ABORT: build failed, not running the oracle on a broken tree ==="
    exit "${BUILD_STATUS}"
fi

# ------------------------------------------------------- upstream equivalence
# The oracle is zero-tolerance by default. It also needs a metallib seeded
# from the release build, which the script handles itself now that the
# release build exists.
echo
echo "--- stage 3: research/run_upstream_equivalence.sh ---"
EQ_T0=$(date +%s)
bash research/run_upstream_equivalence.sh > "${OUT}/equivalence.log" 2>&1
EQ_STATUS=$?
EQ_T1=$(date +%s)
echo "EQUIVALENCE_SCRIPT_EXIT=${EQ_STATUS}"
echo "EQUIVALENCE_SECONDS=$((EQ_T1 - EQ_T0))"
echo "--- grep of the markers the script prints ---"
grep -E '^EQUIVALENCE_(EXACT_STEPS|EXIT)=' "${OUT}/equivalence.log"
echo "--- test-outcome lines ---"
grep -E 'Test run with|Test .* (passed|failed)|error:' "${OUT}/equivalence.log" | tail -n 20
echo "--- tail of equivalence.log ---"
tail -n 40 "${OUT}/equivalence.log"

echo
echo "=== done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "SUMMARY build_exit=${BUILD_STATUS} stale_objects=${STALE} equivalence_exit=${EQ_STATUS}"
exit 0
