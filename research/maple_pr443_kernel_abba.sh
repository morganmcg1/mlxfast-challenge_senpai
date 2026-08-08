#!/usr/bin/env bash
# Research-only (PR #443): counterbalanced per-kernel timing for the halved
# shared gate/up scale plane (`DARKBLOOM_SHARED_SCALE_HALVED`) against the
# shipped default.
#
# The predicted effect is ~-0.39 us on a 7.03 us/call kernel, far below what
# end-to-end decode wall time can resolve, so this uses the GPU-profile hook
# (research/nezuko-pr158-gpuprof-hook.patch, Vendor, research-only) with
# DARKBLOOM_GPU_PROFILE_SPLIT=1 to time the dispatch itself.
#
# Standing rule 36: PR #301's ABBA showed a slot effect large enough to flip the
# sign of a sub-1% per-call difference. `ORDER="off halved halved off"` with
# REPS=6 lays the 24 runs out as 12 adjacent duplexes that alternate
# [off,halved][halved,off]..., i.e. exactly counterbalanced, so a monotone slot
# trend cancels in the duplex contrast and the analysis keeps df=11 instead of
# the df=5 that two separate 3-rep orders would give.
# `research/maple_pr443_duplex_stats.py` also divides out the invariant routed
# twin per run, which is what makes the nuisance additive in logs.
#
# The first run of a session is systematically slow (cold page cache, cold
# pipeline cache), so one unscored warm-up run is issued before slot 01.
#
#   OUT=/tmp/maple-pr443-abba REPS=6 STEPS=33 \
#     bash research/maple_pr443_kernel_abba.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-pr443-abba}"
REPS="${REPS:-6}"
STEPS="${STEPS:-33}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
ORDER="${ORDER:-off halved halved off}"
HOOK_PREAPPLIED=0

mkdir -p "${OUT}"

build_worker() {
  echo "### building worker ($1)"
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null || true
  return "${rc}"
}

cleanup() {
  if [ "${HOOK_PREAPPLIED}" = "1" ]; then
    echo "### GPU-profile hook was already applied on entry; leaving it in place"
    return
  fi
  echo "### reverting GPU-profile hook"
  git apply -R "${PATCH}" || echo "WARNING: hook revert failed; check Vendor tree"
  build_worker "clean" || echo "WARNING: clean rebuild failed; rebuild before submission"
}

if git apply --reverse --check "${PATCH}" 2>/dev/null; then
  HOOK_PREAPPLIED=1
  echo "### GPU-profile hook already present; reusing it"
elif git diff --quiet -- Vendor; then
  git apply "${PATCH}" || exit 3
else
  echo "refusing: Vendor tree is dirty; revert before applying the hook" >&2
  exit 2
fi
trap cleanup EXIT
build_worker "gpu-profile hook" || exit 4

echo "########## unscored warm-up run ##########"
DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
  python3 research/decode_probe.py --steps "${STEPS}" --profile \
    --profile-top 6 --stderr "${OUT}/warmup.err" >"${OUT}/warmup.log" 2>&1
echo "warm-up exit=$?"

echo "########## ${REPS} reps of [${ORDER}] = $((REPS * 2)) duplexes ##########"
OUT="${OUT}" REPS="${REPS}" STEPS="${STEPS}" ORDER="${ORDER}" \
  bash research/maple_shared_qmv_prefetch_abba.sh || exit 5

echo
echo "===== PR #443 kernel timing collected; analyse with ====="
echo "python3 research/maple_pr443_duplex_stats.py --steps ${STEPS} \\"
echo "  --arms off halved ${OUT}/[0-9]*.err"
