#!/usr/bin/env bash
# Research-only (PR #693, R110-B rev4 Stage-0): fresh per-kernel decode profile
# at the current HEAD.
#
# The advisor's Stage-0 sizing came from research/r87a-runs/ceiling.json, which
# predates several promoted frontier changes. Achieved GB/s is us/call in the
# denominator, so a stale us/call silently biases the bandwidth verdict. This
# rebuilds the worker at HEAD with the GPU-profile hook and re-measures.
#
#   OUT=/tmp/edward-r110b-prof STEPS=200 bash research/edward_r110b_qmv_profile.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/edward-r110b-prof}"
STEPS="${STEPS:-200}"
TOP="${TOP:-24}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty; commit before profiling" >&2
  exit 2
fi

echo "### HEAD: $(git rev-parse HEAD)"

cleanup() {
  echo "### reverting GPU-profile hook"
  git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
}

git apply "${PATCH}" || exit 3
trap cleanup EXIT

echo "### building worker (HEAD + gpuprof hook)"
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
[ "${rc}" -eq 0 ] || exit 4

run_slot() {
  local tag="$1"
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      --profile-top "${TOP}" --stderr "${OUT}/${tag}.err" \
      --dump-steps "${OUT}/${tag}.steps" \
      --dump-tokens "${OUT}/${tag}.tokens" \
      >"${OUT}/${tag}.log" 2>&1
  echo "### ${tag} exit=$?"
}

echo "########## unscored warm-up ##########"
run_slot warmup
echo "########## profile run A ##########"
run_slot profA
echo "########## profile run B ##########"
run_slot profB

for t in profA profB; do
  echo "===== ${t} ====="
  cat "${OUT}/${t}.log"
done
