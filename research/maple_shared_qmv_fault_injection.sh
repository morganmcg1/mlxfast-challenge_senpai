#!/usr/bin/env bash
# Research-only (PR #301): fault-injection arm for the shared-expert QMV.
#
# Standing rule 16 -- the upstream-equivalence oracle never dispatches the fused
# shared gate/up kernel, so this PR's 0-divergence teacher-forced results have no
# demonstrated power until a deliberately wrong build is shown to fail. This
# driver applies the env-gated faults from research/maple_pr301_fault_injection.py,
# builds one worker that serves every fault mode, runs the same 128-step
# teacher-forced greedy-token tripwire used for the correctness arms, and then
# reverts the hooks and rebuilds a clean worker so no faulted binary survives.
#
# Both control arms must report 0 divergences and every fault arm must report
# more than 0 for the tripwire to have demonstrated power over that mechanism.
#
#   OUT=/tmp/maple-shared-qmv-fault bash research/maple_shared_qmv_fault_injection.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-shared-qmv-fault}"
STEPS="${STEPS:-128}"
WORKER=".build-worker/release/mlxfast-runtime-worker"

mkdir -p "${OUT}"
SUMMARY="${OUT}/summary.txt"
: >"${SUMMARY}"

# label:prefetch_env:pairwise_env:fault_mode
ARMS=(
  "on-control:1::"
  "on-fault-prefetch_stale:1::prefetch_stale"
  "pairwise-control::1:"
  "pairwise-fault-plane_byte::1:plane_byte"
  "pairwise-fault-plane_shift::1:plane_shift"
)

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
  echo "### reverting fault hooks"
  python3 research/maple_pr301_fault_injection.py revert
  build_worker "clean" || echo "WARNING: clean rebuild failed; rebuild before timing"
}

# `revert` is a hard `git checkout --`, so refuse to run over uncommitted work.
if ! git diff --quiet -- Sources/MLXFastModel/LagunaRuntimeModel.swift \
     Sources/MLXFastModel/LagunaRuntimeWeights.swift; then
  echo "refusing: patched sources are dirty; commit or stash first" >&2
  exit 2
fi

trap cleanup EXIT
python3 research/maple_pr301_fault_injection.py apply | tee "${OUT}/patch.log" || exit 3
build_worker "faulted" || exit 4

index=0
for spec in "${ARMS[@]}"; do
  index=$((index + 1))
  label="${spec%%:*}"
  rest="${spec#*:}"
  prefetch="${rest%%:*}"
  rest="${rest#*:}"
  pairwise="${rest%%:*}"
  fault="${rest#*:}"
  tag="$(printf '%02d' "${index}")-${label}"
  log="${OUT}/${tag}.log"

  {
    echo "########## ${label} (${STEPS}-step teacher-forced tripwire) ##########"
    echo "env: PREFETCH='${prefetch}' PAIRWISE_SCALES='${pairwise}' FAULT='${fault}'"
  } | tee "${log}"

  env DARKBLOOM_SHARED_QMV_PREFETCH="${prefetch}" \
      DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES="${pairwise}" \
      DARKBLOOM_SHARED_QMV_FAULT="${fault}" \
      python3 research/decode_probe.py --steps "${STEPS}" \
        --stderr "${OUT}/${tag}.err" 2>&1 | tee -a "${log}"
  rc="${PIPESTATUS[0]}"

  diverg="$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "${log}" \
    | tail -1 | awk '{print $4}')"
  diverg="${diverg:-NA}"
  first="$(grep -o 'first=([^)]*)' "${log}" | tail -1)"
  echo "${tag} rc=${rc} divergences=${diverg} ${first}" | tee -a "${SUMMARY}"
done

echo
echo "===== fault-injection summary ====="
cat "${SUMMARY}"
