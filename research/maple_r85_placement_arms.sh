#!/usr/bin/env bash
# Research-only (PR #457, R85-C): four-arm counterbalanced per-kernel timing
# that separates the halved shared gate/up scale plane's *placement* effect
# (prep-time allocation sequence and resident footprint) from its *read* effect
# (the bytes the decode kernel actually loads).
#
# PR #443 measured -17.0 us/step on `shared_nvfp4_swiglu_qmv_rows1` and
# +13.5 us/step spread over six untouched kernels. The arms here dose the
# allocation half alone:
#
#   base      DARKBLOOM_SHARED_SCALE_HALVED unset, DOSE=0  -> no halved plane
#   dose_one  DOSE=1                                       -> 1 unread plane
#   halved    DARKBLOOM_SHARED_SCALE_HALVED=1              -> 1 plane, read
#   dose_two  DOSE=2                                       -> 2 unread planes
#
# `dose_one` is the allocation twin of `halved`: identical prep-time build,
# identical +2.56 MB resident footprint, byte-identical decode kernels. If the
# give-back appears in dose_one it is placement; if it appears only in halved it
# is the read pattern; dose_two tests whether the response is monotone in
# footprint (capacity) or not (address aliasing).
#
# Standing rule 36: the slot effect can flip the sign of a sub-1% per-call
# difference, so every contrast is counterbalanced inside each rep. The 12-slot
# ORDER lays out six adjacent duplexes:
#
#   ( 1, 2) base     -> dose_one     ( 7, 8) base     -> dose_two
#   ( 3, 4) halved   -> dose_one     ( 9,10) dose_one -> halved
#   ( 5, 6) dose_two -> base         (11,12) dose_one -> base
#
# so base/dose_one, halved/dose_one and base/dose_two each get one forward and
# one reversed duplex per rep. 12 slots per rep is even, so no offset-0 duplex
# straddles a rep boundary. Reading the same runs at --offset 1 additionally
# yields base/base null duplexes (slots 6-7 within each rep and 12-13 across
# each boundary) for an in-session noise floor, plus a counterbalanced
# dose_one/dose_two contrast at slots (4,5) and (8,9).
#
# The first run of a session is systematically slow (cold page cache, cold
# pipeline cache), so one unscored warm-up run is issued before slot 01.
#
#   OUT=/tmp/maple-r85-arms REPS=6 STEPS=33 \
#     bash research/maple_r85_placement_arms.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-r85-arms}"
REPS="${REPS:-6}"
STEPS="${STEPS:-33}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
ORDER="${ORDER:-base dose_one halved dose_one dose_two base base dose_two dose_one halved dose_one base}"
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

run_slot() {
  local tag="$1" arm="$2"
  unset DARKBLOOM_SHARED_QMV_PREFETCH DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES \
    DARKBLOOM_SHARED_SCALE_HALVED DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE \
    DARKBLOOM_SHARED_SCALE_PAD_PAGES
  case "${arm}" in
    base) : ;;
    dose_one) export DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE=1 ;;
    dose_two) export DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE=2 ;;
    halved) export DARKBLOOM_SHARED_SCALE_HALVED=1 ;;
    halved_pad)
      export DARKBLOOM_SHARED_SCALE_HALVED=1 \
        DARKBLOOM_SHARED_SCALE_PAD_PAGES="${PAD_PAGES:-5}" ;;
    *) echo "unknown arm: ${arm}" >&2; return 64 ;;
  esac
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      --profile-top 6 --stderr "${OUT}/${tag}.err" \
      >"${OUT}/${tag}.log" 2>&1
}

echo "########## unscored warm-up run ##########"
run_slot warmup base
echo "warm-up exit=$?"

slots=0
for arm in ${ORDER}; do slots=$((slots + 1)); done
echo "########## ${REPS} reps x ${slots} slots = $((REPS * slots)) runs ##########"

idx=0
for rep in $(seq 1 "${REPS}"); do
  for arm in ${ORDER}; do
    idx=$((idx + 1))
    tag=$(printf "%02d-rep%s-%s" "${idx}" "${rep}" "${arm}")
    echo "=== ${tag} ==="
    run_slot "${tag}" "${arm}"
    status=$?
    grep -E "teacher-forced|per steady step" "${OUT}/${tag}.log"
    grep -E "halved scale plane" "${OUT}/${tag}.log" | head -2
    echo "exit=${status}"
    [ "${status}" -eq 0 ] || exit "${status}"
  done
done

echo
echo "===== R85-C placement arms collected; analyse with ====="
for pair in "base dose_one" "halved dose_one" "base dose_two" "base base"; do
  echo "python3 research/maple_r85_arm_stats.py --steps ${STEPS} \\"
  echo "  --arms ${pair} --strip-infix _hs_ _ps_ ${OUT}/[0-9]*.err"
done
