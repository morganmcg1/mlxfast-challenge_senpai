#!/usr/bin/env bash
# Research-only three-arm ABBA driver for PR #441 (decode router block tournament).
#
#   research/nezuko_q12_abba.sh OUTDIR [BLOCKS] [STEPS] [ORDER] [PREFILL]
#
# Arms (DARKBLOOM_DECODE_ROUTER_TOURNAMENT):
#   off    = 0       incumbent full-256 bitonic network, 12 charged TG barriers
#   on     = 1       two-phase block tournament, 3 charged TG barriers
#   inert  = inert   incumbent network recompiled under a distinct kernel name
#                    with a no-op MSL suffix (standing rule 3 invariant control)
#
# on-off is the headline, inert-off is the null that prices pipeline identity and
# kernel-cache slot placement, and on-inert is the algorithm net of that null.
# "off" is passed as the explicit string 0, never as an empty or absent variable,
# because the dispatcher treats any value other than "0" as tournament-on.
#
# Standing rule 36: an arm must not be pinned to a slot position. ORDER defaults
# to the palindrome "off on inert inert on off"; run it a second time with
# "inert on off off on inert" so every arm visits both slot kinds, then hand both
# output directories to research/nezuko_q12_stats.py.
#
# Standing rule 17: cover the second axis with
#   research/nezuko_q12_abba.sh OUT 1 8 "off on inert inert on off" 1
set -uo pipefail
OUTDIR="${1:?outdir}"
BLOCKS="${2:-4}"
STEPS="${3:-256}"
ORDER="${4:-off on inert inert on off}"
PREFILL="${5:-0}"
EXTRA=()
[[ "${PREFILL}" == "1" ]] && EXTRA+=(--prefill)
mkdir -p "${OUTDIR}"

run_arm() {
  local arm="$1" tag="$2" flag
  case "${arm}" in
    off)   flag=0     ;;
    on)    flag=1     ;;
    inert) flag=inert ;;
    *)     echo "unknown arm ${arm}" >&2; return 1 ;;
  esac
  echo "=== $(date -u +%H:%M:%S) ${tag} arm=${arm} flag=${flag}"
  DARKBLOOM_DECODE_ROUTER_TOURNAMENT="${flag}" \
  python3 research/decode_probe.py --steps "${STEPS}" "${EXTRA[@]+${EXTRA[@]}}" \
    --dump-steps "${OUTDIR}/${tag}.steps" \
    --stderr "${OUTDIR}/${tag}.err" \
    > "${OUTDIR}/${tag}.log" 2>&1
  grep -E "^(teacher-forced|decode steps=|prefill)" "${OUTDIR}/${tag}.log"
}

i=0
run_seq() { i=$((i + 1)); run_arm "$1" "$(printf 'b%02d_s%02d_%s' "${blk}" "${i}" "$1")"; }

blk=0
run_seq off   # discarded warm-up / page-cache primer
for ((blk = 1; blk <= BLOCKS; blk++)); do
  for arm in ${ORDER}; do run_seq "${arm}"; done
done
echo "=== $(date -u +%H:%M:%S) done ${i} runs"
