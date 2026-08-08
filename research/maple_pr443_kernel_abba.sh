#!/usr/bin/env bash
# Research-only (PR #443): per-kernel ABBA timing for the halved shared gate/up
# scale plane (`DARKBLOOM_SHARED_SCALE_HALVED`) against the shipped default.
#
# The predicted effect is ~-0.39 us on a 7.03 us/call kernel, far below what
# end-to-end decode wall time can resolve, so this uses the GPU-profile hook
# (research/nezuko-pr158-gpuprof-hook.patch, Vendor, research-only) with
# DARKBLOOM_GPU_PROFILE_SPLIT=1 to time the dispatch itself.
#
# Standing rule 36: PR #301's ABBA showed a slot effect large enough to flip the
# sign of a sub-1% per-call difference, so both ABBA orders are run here and the
# invariant routed twin is read out of the same profiles as a control. A result
# is only reported when both orders agree in sign.
#
#   OUT=/tmp/maple-pr443-abba REPS=3 STEPS=33 \
#     bash research/maple_pr443_kernel_abba.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-pr443-abba}"
REPS="${REPS:-3}"
STEPS="${STEPS:-33}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
ORDERS=("off halved halved off" "halved off off halved")

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
  echo "### reverting GPU-profile hook"
  git apply -R "${PATCH}" || echo "WARNING: hook revert failed; check Vendor tree"
  build_worker "clean" || echo "WARNING: clean rebuild failed; rebuild before submission"
}

if ! git diff --quiet -- Vendor; then
  echo "refusing: Vendor tree is dirty; revert before applying the hook" >&2
  exit 2
fi

git apply "${PATCH}" || exit 3
trap cleanup EXIT
build_worker "gpu-profile hook" || exit 4

for order_index in 0 1; do
  order="${ORDERS[${order_index}]}"
  dir="${OUT}/order$((order_index + 1))"
  mkdir -p "${dir}"
  echo "########## ABBA order $((order_index + 1)): ${order} ##########"
  OUT="${dir}" REPS="${REPS}" STEPS="${STEPS}" ORDER="${order}" \
    bash research/maple_shared_qmv_prefetch_abba.sh || exit 5
done

echo
echo "===== PR #443 kernel ABBA collected; analyse with ====="
for order_index in 0 1; do
  echo "python3 research/maple_shared_qmv_kernel_stats.py --steps ${STEPS} \\"
  echo "  --kernel shared_nvfp4_swiglu_qmv_rows1 --per-step 39 \\"
  echo "  ${OUT}/order$((order_index + 1))/*.err"
done
