#!/usr/bin/env bash
# Research-only (PR #571, R103-A rung 1): position-matched ABBA e2e decode
# timing of the two revisions bracketing the round-100 frontier adoption.
#
# Slots per repetition, reversed on odd repetitions:
#
#   rep even   oldA  old   new   oldB
#   rep odd    oldB  new   old   oldA
#
# Over any even number of repetitions the real contrast (new - old) is
# position-matched on the two interior slots and the rule-79 identical-code
# null (oldB - oldA) is position-matched on the two exterior slots, in the same
# session. Exterior slots carry more session drift, so the null is a
# conservative upper bound on the noise floor of the real contrast.
#
# The first two repetitions (one full even/odd cycle, so discarding them cannot
# unbalance position matching) are warm-up and excluded from the analysis.
#
# No GPU-profile hook and no source edit: this rung times the shipped runtime
# end to end. The rule-75 Sources+Vendor digest is published before and after
# and must be unchanged.
#
#   SNAP=/tmp/maple-r103a-snap OUT=/tmp/maple-r103a/rung1 REPS=26 STEPS=250 \
#     bash research/maple-frieren-r103a-abba.sh
set -uo pipefail

SNAP="${SNAP:-/tmp/maple-r103a-snap}"
OUT="${OUT:-/tmp/maple-r103a/rung1}"
REPS="${REPS:-26}"
STEPS="${STEPS:-250}"
WARMUP_REPS="${WARMUP_REPS:-2}"
# Rung 2 reuses this driver with PROFILE=1 SPLIT=1 against the hooked snapshots.
# SPLIT=1 buys per-kernel attribution by putting one dispatch in each command
# buffer, which inflates absolute GPU time; it is an arm-vs-arm relative
# estimator only (rule 43), never an end-to-end magnitude.
PROFILE="${PROFILE:-0}"
SPLIT="${SPLIT:-0}"
PROFILE_ARGS=""
[ "${PROFILE}" = "1" ] && PROFILE_ARGS="--profile --profile-top 60"
SLOTS=(oldA old new oldB)

mkdir -p "${OUT}"
PROV="${OUT}/provenance.txt"
: >"${PROV}"
log() { printf '%s\n' "$*" | tee -a "${PROV}"; }

tree_digest() {
  find Sources Vendor -type f -print0 | sort -z | xargs -0 shasum -a 256 \
    | shasum -a 256 | awk '{print $1}'
}

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor tree is dirty" >&2
  exit 2
fi
for a in "${SLOTS[@]}"; do
  [ -x "${SNAP}/${a}/mlxfast-runtime-worker" ] || {
    echo "refusing: missing snapshot ${SNAP}/${a}" >&2; exit 3; }
done
if cmp -s "${SNAP}/old/mlxfast-runtime-worker" \
          "${SNAP}/new/mlxfast-runtime-worker"; then
  echo "refusing: old and new binaries are byte-identical" >&2; exit 4
fi
cmp -s "${SNAP}/oldA/mlxfast-runtime-worker" "${SNAP}/oldB/mlxfast-runtime-worker" \
  || { echo "refusing: null arms oldA/oldB are not byte-identical" >&2; exit 5; }

DIGEST_BEFORE="$(tree_digest)"
log "head=$(git rev-parse HEAD)"
log "digest_before=${DIGEST_BEFORE}"
log "reps=${REPS} steps=${STEPS} warmup_reps=${WARMUP_REPS} slots=${SLOTS[*]}"
log "host=$(sysctl -n machdep.cpu.brand_string)"
shasum -a 256 "${SNAP}"/*/mlxfast-runtime-worker | tee -a "${PROV}"

finish() {
  local after; after="$(tree_digest)"
  log "digest_after=${after}"
  [ "${after}" = "${DIGEST_BEFORE}" ] \
    && log "PASS(rule 75): Sources+Vendor unchanged across the timed run" \
    || log "FAIL(rule 75): Sources+Vendor changed during the timed run"
}
trap finish EXIT

run_slot() {
  local tag="$1" arm="$2"
  DECODE_PROBE_WORKER="${SNAP}/${arm}/mlxfast-runtime-worker" \
  DARKBLOOM_GPU_PROFILE="${PROFILE}" \
  DARKBLOOM_GPU_PROFILE_SPLIT="${SPLIT}" \
    python3 research/decode_probe.py --steps "${STEPS}" ${PROFILE_ARGS} \
      --stderr "${OUT}/${tag}.err" \
      --dump-steps "${OUT}/${tag}.steps" \
      --dump-tokens "${OUT}/${tag}.tokens" \
      >"${OUT}/${tag}.log" 2>&1
}

: >"${OUT}/index.tsv"
printf 'rep\tposition\tarm\ttag\n' >>"${OUT}/index.tsv"

for rep in $(seq 0 $((REPS - 1))); do
  if [ $((rep % 2)) -eq 0 ]; then
    order=("${SLOTS[@]}")
  else
    order=(); for ((i = ${#SLOTS[@]} - 1; i >= 0; i--)); do order+=("${SLOTS[$i]}"); done
  fi
  pos=0
  for arm in "${order[@]}"; do
    pos=$((pos + 1))
    tag=$(printf "rep%02d-pos%d-%s" "${rep}" "${pos}" "${arm}")
    echo "=== ${tag} ==="
    run_slot "${tag}" "${arm}"
    rc=$?
    printf '%d\t%d\t%s\t%s\n' "${rep}" "${pos}" "${arm}" "${tag}" \
      >>"${OUT}/index.tsv"
    grep -E "^decode steps=|^teacher-forced" "${OUT}/${tag}.log" \
      || echo "  (no summary; exit=${rc})"
  done
done

echo "########## G0.2 token parity across every slot ##########"
cksum "${OUT}"/rep*.tokens | awk '{print $1, $3}' | tee "${OUT}/tokens.cksum"
awk '{print $1}' "${OUT}/tokens.cksum" | sort -u | wc -l \
  | xargs -I{} echo "distinct token-stream checksums: {} (must be 1)"
echo "########## done ##########"
