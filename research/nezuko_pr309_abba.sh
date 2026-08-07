#!/usr/bin/env bash
# Research-only seven-arm ABBA driver for PR #309 (persistent grid-stride QKV).
#
#   research/nezuko_pr309_abba.sh /tmp/nez309/abba [BLOCKS] [STEPS]
#
# Arms are (R1_SIMDGROUPS : NORM_QKV_FUSE : TOTAL_THREADGROUPS):
#   a0   = 2 :0:0     stock geometry, no fold                     (anchor)
#   G640 = 16:0:0     fused geometry, one row per simdgroup, no fold
#   R640 = 16:3:0     fused geometry, fold computed, rmsnorm still dispatched
#   N640 = 16:1:0     fused geometry, fold replaces the rmsnorm dispatch (PR #48)
#   G128 = 16:0:128   persistent grid, 5 rows/sg (h64), no fold
#   R128 = 16:3:128   persistent grid, redundant reduction
#   N128 = 16:1:128   persistent grid, fold replaces the rmsnorm dispatch
#
# G128-G640 prices the multi-row change on its own, R128-G128 prices the
# amortised redundant reduction, N128-R128 prices the dispatch refund, and
# N128-a0 is the headline.
#
# Each block is the palindrome a0 G640 R640 N640 G128 R128 N128 N128 R128 G128
# N640 R640 G640 a0, so monotone thermal/allocator drift cancels inside a block.
#
# Rule 17 (measure both axes when flipping a DARKBLOOM_* flag) is served by
# re-running with PREFILL=1 and a short ARM_SEQ, e.g.
#   PREFILL=1 ARM_SEQ="a0 N128 N128 a0 a0 N128" research/nezuko_pr309_abba.sh OUT 1 8
set -uo pipefail
OUTDIR="${1:?outdir}"
BLOCKS="${2:-4}"
STEPS="${3:-192}"
PREFILL="${PREFILL:-0}"
ARM_SEQ="${ARM_SEQ:-a0 G640 R640 N640 G128 R128 N128 N128 R128 G128 N640 R640 G640 a0}"
EXTRA=()
[[ "${PREFILL}" == "1" ]] && EXTRA+=(--prefill)
mkdir -p "${OUTDIR}"

run_arm() {
  local arm="$1" tag="$2" sg nf tg
  case "${arm}" in
    a0)   sg=2;  nf=0; tg=0   ;;
    G640) sg=16; nf=0; tg=0   ;;
    R640) sg=16; nf=3; tg=0   ;;
    N640) sg=16; nf=1; tg=0   ;;
    G128) sg=16; nf=0; tg=128 ;;
    R128) sg=16; nf=3; tg=128 ;;
    N128) sg=16; nf=1; tg=128 ;;
    *)    echo "unknown arm ${arm}" >&2; return 1 ;;
  esac
  echo "=== $(date -u +%H:%M:%S) ${tag} sg=${sg} nf=${nf} tg=${tg}"
  DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS="${sg}" \
  DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE="${nf}" \
  DARKBLOOM_DECODE_NVFP4_QKV_TOTAL_THREADGROUPS="${tg}" \
  python3 research/decode_probe.py --steps "${STEPS}" "${EXTRA[@]+${EXTRA[@]}}" \
    --dump-steps "${OUTDIR}/${tag}.steps" \
    --stderr "${OUTDIR}/${tag}.err" \
    > "${OUTDIR}/${tag}.log" 2>&1
  grep -E "^(teacher-forced|decode steps=|prefill)" "${OUTDIR}/${tag}.log"
}

i=0
run_seq() { i=$((i + 1)); run_arm "$1" "$(printf 'b%02d_s%02d_%s' "${blk}" "${i}" "$1")"; }

blk=0
run_seq a0   # discarded warm-up / cache-primer
for ((blk = 1; blk <= BLOCKS; blk++)); do
  for arm in ${ARM_SEQ}; do run_seq "${arm}"; done
done
echo "=== $(date -u +%H:%M:%S) done ${i} runs"
