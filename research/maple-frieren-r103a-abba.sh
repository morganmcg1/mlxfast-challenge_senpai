#!/usr/bin/env bash
# Research-only (PR #571, R103-A): position-matched end-to-end decode timing of
# several revisions/arms of the Laguna runtime in one session.
#
# An arm is "name:snapshot[:K=V,K=V]": a worker binary plus the environment
# that selects its variant. Two arms may share one snapshot when the mechanism
# has a process-once env switch, which removes build-to-build variation from
# that contrast entirely.
#
# DESIGN=reverse (rung 1, 4 arms x 1 slot): the slot order is reversed on odd
# repetitions, so each arm spends half its slots at each of its two positions.
#
#   rep even   oldA  old   new   oldB
#   rep odd    oldB  new   old   oldA
#
# DESIGN=rotate (rung 2, N arms x 2 slots): each repetition is the palindrome
# "order + reverse(order)" and `order` is rotated by one arm per repetition.
# The palindrome cancels linear drift inside every arm; the rotation balances
# the non-linear position profile, which rung 1 measured at about +17 us/step
# for interior versus exterior slots. Each arm's own two slots are an
# identical-code null at lag 2N-1, 2N-3, ... and the rotation gives every arm
# every lag, so the nulls are reported per lag and never pooled (doc S 1.12 A2).
#
#   rep 0    A B C C B A
#   rep 1    B C A A C B
#   rep 2    C A B B A C
#
# The first WARMUP_REPS repetitions are discarded; make that a whole number of
# rotation cycles so discarding cannot unbalance the design.
#
# No GPU-profile hook and no source edit: this times the shipped runtime end to
# end. The rule-75 Sources+Vendor digest is published before and after and must
# be unchanged.
#
#   SNAP=/tmp/maple-r103a-snap OUT=/tmp/maple-r103a/rung1 REPS=26 STEPS=250 \
#     bash research/maple-frieren-r103a-abba.sh
set -uo pipefail

SNAP="${SNAP:-/tmp/maple-r103a-snap}"
OUT="${OUT:-/tmp/maple-r103a/rung1}"
REPS="${REPS:-26}"
STEPS="${STEPS:-250}"
WARMUP_REPS="${WARMUP_REPS:-2}"
DESIGN="${DESIGN:-reverse}"
ARMS="${ARMS:-oldA:oldA old:old new:new oldB:oldB}"
# Space-separated "snapA:snapB" pairs whose worker binaries must differ / match.
ASSERT_DIFFER="${ASSERT_DIFFER:-old:new}"
ASSERT_SAME="${ASSERT_SAME:-oldA:oldB}"
# PROFILE=1 SPLIT=1 buys per-kernel attribution by putting one dispatch in each
# command buffer, which inflates absolute GPU time; it is an arm-vs-arm
# relative estimator only (rule 43), never an end-to-end magnitude.
PROFILE="${PROFILE:-0}"
SPLIT="${SPLIT:-0}"
PROFILE_ARGS=""
[ "${PROFILE}" = "1" ] && PROFILE_ARGS="--profile --profile-top 60"

ARM_NAMES=(); ARM_SNAP=(); ARM_ENV=()
for spec in ${ARMS}; do
  name="${spec%%:*}"; rest="${spec#*:}"; snap="${rest%%:*}"
  [ "${rest}" = "${snap}" ] && envs="" || envs="${rest#*:}"
  ARM_NAMES+=("${name}"); ARM_SNAP+=("${snap}"); ARM_ENV+=("${envs}")
done
NARMS=${#ARM_NAMES[@]}

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
for a in "${ARM_SNAP[@]}"; do
  [ -x "${SNAP}/${a}/mlxfast-runtime-worker" ] || {
    echo "refusing: missing snapshot ${SNAP}/${a}" >&2; exit 3; }
done
for pair in ${ASSERT_DIFFER}; do
  cmp -s "${SNAP}/${pair%%:*}/mlxfast-runtime-worker" \
         "${SNAP}/${pair##*:}/mlxfast-runtime-worker" \
    && { echo "refusing: ${pair} binaries are byte-identical" >&2; exit 4; }
done
for pair in ${ASSERT_SAME}; do
  cmp -s "${SNAP}/${pair%%:*}/mlxfast-runtime-worker" \
         "${SNAP}/${pair##*:}/mlxfast-runtime-worker" \
    || { echo "refusing: ${pair} binaries are not byte-identical" >&2; exit 5; }
done

DIGEST_BEFORE="$(tree_digest)"
log "head=$(git rev-parse HEAD)"
log "digest_before=${DIGEST_BEFORE}"
log "reps=${REPS} steps=${STEPS} warmup_reps=${WARMUP_REPS} design=${DESIGN}"
log "arms=${ARMS}"
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
  local tag="$1" idx="$2"
  local ev=()
  [ -n "${ARM_ENV[$idx]}" ] && IFS=',' read -ra ev <<<"${ARM_ENV[$idx]}"
  env ${ev[@]+"${ev[@]}"} \
    DECODE_PROBE_WORKER="${SNAP}/${ARM_SNAP[$idx]}/mlxfast-runtime-worker" \
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
  order=()
  if [ "${DESIGN}" = "rotate" ]; then
    for ((i = 0; i < NARMS; i++)); do order+=($(((rep + i) % NARMS))); done
    for ((i = NARMS - 1; i >= 0; i--)); do order+=("${order[$i]}"); done
  elif [ $((rep % 2)) -eq 0 ]; then
    for ((i = 0; i < NARMS; i++)); do order+=("${i}"); done
  else
    for ((i = NARMS - 1; i >= 0; i--)); do order+=("${i}"); done
  fi
  pos=0
  for idx in "${order[@]}"; do
    pos=$((pos + 1))
    tag=$(printf "rep%02d-pos%d-%s" "${rep}" "${pos}" "${ARM_NAMES[$idx]}")
    echo "=== ${tag} ==="
    run_slot "${tag}" "${idx}"
    rc=$?
    printf '%d\t%d\t%s\t%s\n' "${rep}" "${pos}" "${ARM_NAMES[$idx]}" "${tag}" \
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
