#!/usr/bin/env bash
# Research-only (PR #443): fault-injection battery for the halved shared
# gate/up scale plane.
#
# Standing rule 16 -- a 0-divergence teacher-forced run has no demonstrated
# power until a deliberately wrong build of the same mechanism is shown to
# fail. This driver applies the env-gated faults from
# research/maple_pr443_fault_injection.py, builds one worker that serves every
# mode, runs the arms, then reverts the hooks and rebuilds a clean worker so no
# faulted binary survives.
#
# The fault ladder is ordered by decreasing subtlety so the detection floor is
# bounded rather than assumed:
#   plane_byte     one byte of the halved plane (1 / 65664)
#   plane_column   one byte per plane row       (1024 / 65664)
#   header_drop    the 128-byte patch header is ignored by the kernel
#   plane_shift    the whole plane data region shifts one byte
#   activation_zero the fused shared activation is zeroed (power ceiling)
# Both control arms must report 0 divergences. The first mode in the ladder
# that diverges is the demonstrated sensitivity floor; anything finer than it
# is undetected and must be reported as such.
#
# MODE=freerun swaps the teacher-forced tripwire for a self-feeding free run
# (compounding rather than per-step argmax). BOOTSTRAP=<token id> avoids the
# fixture's own period-3 attractor.
#
#   OUT=/tmp/maple-pr443-fault bash research/maple_pr443_fault_battery.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-pr443-fault}"
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

# label:halved_env:fault_mode
ARMS=(
  "off-control::"
  "on-control:1:"
  "on-fault-plane_byte:1:plane_byte"
  "on-fault-plane_column:1:plane_column"
  "on-fault-header_drop:1:header_drop"
  "on-fault-plane_shift:1:plane_shift"
  "on-fault-activation_zero:1:activation_zero"
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
  python3 research/maple_pr443_fault_injection.py revert
  build_worker "clean" || echo "WARNING: clean rebuild failed; rebuild before timing"
}

# `revert` is a hard `git checkout --`, so refuse to run over uncommitted work.
if ! git diff --quiet -- Sources/MLXFastModel/LagunaRuntimeModel.swift \
     Sources/MLXFastModel/LagunaRuntimeWeights.swift; then
  echo "refusing: patched sources are dirty; commit or stash first" >&2
  exit 2
fi

trap cleanup EXIT
python3 research/maple_pr443_fault_injection.py apply | tee "${OUT}/patch.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || exit 3
python3 research/maple_pr443_fault_injection.py check | tee -a "${OUT}/patch.log"
build_worker "faulted" || exit 4

index=0
for spec in "${ARMS[@]}"; do
  index=$((index + 1))
  label="${spec%%:*}"
  rest="${spec#*:}"
  halved="${rest%%:*}"
  fault="${rest#*:}"
  tag="$(printf '%02d' "${index}")-${label}"
  log="${OUT}/${tag}.log"

  {
    echo "########## ${label} (${STEPS}-step ${MODE_LABEL}) ##########"
    echo "env: SHARED_SCALE_HALVED='${halved}' FAULT='${fault}'"
  } | tee "${log}"

  probe_extra=""
  if [ "${MODE}" = "freerun" ]; then
    probe_extra="--free-run --dump-tokens ${OUT}/${tag}.tokens"
    [ -n "${BOOTSTRAP}" ] && probe_extra="${probe_extra} --free-run-bootstrap ${BOOTSTRAP}"
  fi

  env DARKBLOOM_SHARED_SCALE_HALVED="${halved}" \
      DARKBLOOM_SHARED_QMV_FAULT="${fault}" \
      python3 research/decode_probe.py --steps "${STEPS}" \
        ${probe_extra} --stderr "${OUT}/${tag}.err" 2>&1 | tee -a "${log}"
  rc="${PIPESTATUS[0]}"

  cert="$(grep -c 'shared gate/up halved scale plane' "${OUT}/${tag}.err" 2>/dev/null)"
  if [ "${MODE}" = "freerun" ]; then
    hash="$(grep -o 'hash=[0-9a-f]*' "${log}" | tail -1 | cut -d= -f2)"
    echo "${tag} rc=${rc} cert=${cert:-0} hash=${hash:-NA}" | tee -a "${SUMMARY}"
  else
    diverg="$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "${log}" \
      | tail -1 | awk '{print $4}')"
    diverg="${diverg:-NA}"
    first="$(grep -o 'first=([^)]*)' "${log}" | tail -1)"
    echo "${tag} rc=${rc} cert=${cert:-0} divergences=${diverg} ${first}" | tee -a "${SUMMARY}"
  fi
done

echo
echo "===== PR #443 fault-injection summary ====="
cat "${SUMMARY}"
