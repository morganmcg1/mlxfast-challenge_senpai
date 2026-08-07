#!/usr/bin/env bash
# Research-only six-arm ABBA driver for the PR #48 fusion deconfound.
#
#   research/nezuko_pr48_abba.sh /tmp/nez298/abba [BLOCKS] [STEPS]
#
# Arms (DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS : DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE)
#   0  = 2:0   stock geometry, no fold
#   RV = 2:3   stock geometry, fold computed but rmsnorm still dispatched (redundant)
#   V  = 2:1   stock geometry, fold replaces the rmsnorm dispatch
#   G  = 16:0  fused geometry, no fold
#   R  = 16:3  fused geometry, redundant reduction
#   N  = 16:1  fused geometry, fold replaces the rmsnorm dispatch (== PR #48)
#
# Each block is the palindrome 0 RV V G R N N R G V RV 0 so any monotone
# thermal/allocator drift cancels inside the block.
#
# Rule 17 (measure both axes when flipping a DARKBLOOM_* flag) is served by
# re-running with PREFILL=1 and a short ARM_SEQ, e.g.
#   PREFILL=1 ARM_SEQ="0 N N 0 0 N" ./research/nezuko_pr48_abba.sh OUT 1 8
set -uo pipefail
OUTDIR="${1:?outdir}"
BLOCKS="${2:-4}"
STEPS="${3:-200}"
PREFILL="${PREFILL:-0}"
ARM_SEQ="${ARM_SEQ:-0 RV V G R N N R G V RV 0}"
EXTRA=()
[[ "${PREFILL}" == "1" ]] && EXTRA+=(--prefill)
mkdir -p "${OUTDIR}"

run_arm() {
  local arm="$1" tag="$2" sg nf
  case "${arm}" in
    0)  sg=2;  nf=0 ;;
    RV) sg=2;  nf=3 ;;
    V)  sg=2;  nf=1 ;;
    G)  sg=16; nf=0 ;;
    R)  sg=16; nf=3 ;;
    N)  sg=16; nf=1 ;;
    *)  echo "unknown arm ${arm}" >&2; return 1 ;;
  esac
  echo "=== $(date -u +%H:%M:%S) ${tag} sg=${sg} nf=${nf}"
  DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS="${sg}" \
  DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE="${nf}" \
  python3 research/decode_probe.py --steps "${STEPS}" "${EXTRA[@]+${EXTRA[@]}}" \
    --dump-steps "${OUTDIR}/${tag}.steps" \
    --stderr "${OUTDIR}/${tag}.err" \
    > "${OUTDIR}/${tag}.log" 2>&1
  grep -E "^(teacher-forced|decode steps=|prefill)" "${OUTDIR}/${tag}.log"
}

i=0
run_seq() { i=$((i + 1)); run_arm "$1" "$(printf 'b%02d_s%02d_%s' "${blk}" "${i}" "$1")"; }

blk=0
run_seq 0   # discarded warm-up / cache-primer
for ((blk = 1; blk <= BLOCKS; blk++)); do
  for arm in ${ARM_SEQ}; do run_seq "${arm}"; done
done
echo "=== $(date -u +%H:%M:%S) done ${i} runs"
