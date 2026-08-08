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
# MODE=freerun swaps the teacher-forced tripwire for a self-feeding free run.
# Teacher forcing resets the trajectory every step, so it only ever compares
# single-step argmaxes against the golden; a free run compounds any difference,
# so two builds share a token hash only if every step agreed.
#
# Compounding only buys sensitivity if the trajectory is not in a short
# attractor, and this fixture's own continuation is the period-3 cycle
# 509/902/5991 -- self-feeding it is then identical to teacher forcing. Set
# BOOTSTRAP=<token id> to feed a different token at step 0 and get an
# open-ended 256-step trajectory instead. The probe prints the observed
# distinct-token count and cycle period so this is checked, not assumed.
#
#   OUT=/tmp/maple-shared-qmv-fault bash research/maple_shared_qmv_fault_injection.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-shared-qmv-fault}"
MODE="${MODE:-tripwire}"
BOOTSTRAP="${BOOTSTRAP:-}"
if [ "${MODE}" = "freerun" ]; then
  STEPS="${STEPS:-256}"
  MODE_LABEL="self-fed free run"
else
  STEPS="${STEPS:-128}"
  MODE_LABEL="teacher-forced tripwire"
fi

mkdir -p "${OUT}"
SUMMARY="${OUT}/summary.txt"
: >"${SUMMARY}"

# label:prefetch_env:pairwise_env:fault_mode
if [ "${MODE}" = "freerun" ]; then
  # With FAULT unset every fault branch expands to a no-op, so the three
  # unfaulted arms measure the shipped guards on this one faulted-source build.
  # prefetch_zero and plane_shift are the two faults the teacher-forced battery
  # already detects; they are the positive controls that make an all-arms-match
  # hash table evidence instead of a silent detector failure.
  ARMS=(
    "off:::"
    "on:1::"
    "pairwise::1:"
    "on-fault-prefetch_stale:1::prefetch_stale"
    "on-fault-prefetch_zero:1::prefetch_zero"
    "pairwise-fault-plane_byte::1:plane_byte"
    "pairwise-fault-plane_shift::1:plane_shift"
  )
else
  ARMS=(
    "on-control:1::"
    "on-fault-prefetch_stale:1::prefetch_stale"
    "on-fault-prefetch_zero:1::prefetch_zero"
    "on-fault-activation_zero:1::activation_zero"
    "pairwise-control::1:"
    "pairwise-fault-plane_byte::1:plane_byte"
    "pairwise-fault-plane_shift::1:plane_shift"
  )
fi

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
python3 research/maple_pr301_fault_injection.py apply | tee "${OUT}/patch.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || exit 3
python3 research/maple_pr301_fault_injection.py check | tee -a "${OUT}/patch.log"
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
    echo "########## ${label} (${STEPS}-step ${MODE_LABEL}) ##########"
    echo "env: PREFETCH='${prefetch}' PAIRWISE_SCALES='${pairwise}' FAULT='${fault}'"
  } | tee "${log}"

  probe_extra=""
  if [ "${MODE}" = "freerun" ]; then
    probe_extra="--free-run --dump-tokens ${OUT}/${tag}.tokens"
    [ -n "${BOOTSTRAP}" ] && probe_extra="${probe_extra} --free-run-bootstrap ${BOOTSTRAP}"
  fi

  env DARKBLOOM_SHARED_QMV_PREFETCH="${prefetch}" \
      DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES="${pairwise}" \
      DARKBLOOM_SHARED_QMV_FAULT="${fault}" \
      python3 research/decode_probe.py --steps "${STEPS}" \
        ${probe_extra} --stderr "${OUT}/${tag}.err" 2>&1 | tee -a "${log}"
  rc="${PIPESTATUS[0]}"

  if [ "${MODE}" = "freerun" ]; then
    hash="$(grep -o 'hash=[0-9a-f]*' "${log}" | tail -1 | cut -d= -f2)"
    echo "${tag} rc=${rc} hash=${hash:-NA}" | tee -a "${SUMMARY}"
  else
    diverg="$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "${log}" \
      | tail -1 | awk '{print $4}')"
    diverg="${diverg:-NA}"
    first="$(grep -o 'first=([^)]*)' "${log}" | tail -1)"
    echo "${tag} rc=${rc} divergences=${diverg} ${first}" | tee -a "${SUMMARY}"
  fi
done

echo
echo "===== fault-injection summary ====="
cat "${SUMMARY}"
