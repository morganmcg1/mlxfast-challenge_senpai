#!/usr/bin/env bash
# Research-only six-arm ABBA driver for the QKV-GEMV threadgroup-packing curve.
#
#   research/tanjiro_packing_abba.sh /tmp/tanjiro/abba [BLOCKS] [STEPS]
#
# One axis only: DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS. The norm fold is
# pinned off (DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE=0) so the fold confound that
# PR #298 had to untangle cannot re-enter, and so no threadgroup memory scales
# with S.
#
# Arm labels are deliberately the PR #48 label alphabet so
# research/nezuko_pr48_stats.py can score this sweep with its estimator, OLS,
# and interference report reused verbatim (reference arm = "0" = the shipped
# default S=2):
#
#   0  = S=2   shipped default (reference)
#   RV = S=1   one simdgroup per threadgroup
#   V  = S=4
#   G  = S=8
#   R  = S=16  the PR #298 winner geometry
#   N  = S=32  1024 threads/threadgroup, the Metal maximum
#
# Total simdgroups, rows per simdgroup (1), arithmetic, and bytes read are
# identical in every arm; only how simdgroups are packed into threadgroups
# changes. Each block is the palindrome 0 RV V G R N N R G V RV 0 so monotone
# thermal/allocator drift cancels inside the block.
#
# Rule 17 (measure both axes when flipping a DARKBLOOM_* flag) is served by
# re-running with PREFILL=1 and a short ARM_SEQ, e.g.
#   PREFILL=1 ARM_SEQ="0 R R 0 0 R" ./research/tanjiro_packing_abba.sh OUT 1 8
set -uo pipefail
OUTDIR="${1:?outdir}"
BLOCKS="${2:-3}"
STEPS="${3:-200}"
PREFILL="${PREFILL:-0}"
ARM_SEQ="${ARM_SEQ:-0 RV V G R N N R G V RV 0}"
EXTRA=()
[[ "${PREFILL}" == "1" ]] && EXTRA+=(--prefill)
mkdir -p "${OUTDIR}"

run_arm() {
  local arm="$1" tag="$2" sg
  case "${arm}" in
    0)  sg=2 ;;
    RV) sg=1 ;;
    V)  sg=4 ;;
    G)  sg=8 ;;
    R)  sg=16 ;;
    N)  sg=32 ;;
    *)  echo "unknown arm ${arm}" >&2; return 1 ;;
  esac
  echo "=== $(date -u +%H:%M:%S) ${tag} S=${sg}"
  DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS="${sg}" \
  DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE=0 \
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
