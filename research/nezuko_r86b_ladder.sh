#!/usr/bin/env bash
# Research-only R86-B in-situ boundary-price ladder driver.
#
#   research/nezuko_r86b_ladder.sh /tmp/r86b/ladder [BLOCKS] [STEPS]
#
# Arms are `<mode><inserts>`, where `inserts` is the number of injected
# dependent ops per decoder layer. Laguna has 40 decoder layers, so
# k = 40 * inserts inserted boundaries per decode step:
#   w0 w2 w4 w8 w16   WIDE: chained BF16 multiplies of the live [1,1,2048]
#                     hidden row (4096 B read + 4096 B written per dispatch)
#   t0 t2 t4 t8 t16   TINY: the same chain on a [1] BF16 scratch, folded back
#                     with one broadcast add present at every rung
#
# Each block is a palindrome, so monotone thermal/allocator drift cancels
# inside the block. `w0` is byte-identical to the disarmed instrument.
set -uo pipefail
OUTDIR="${1:?outdir}"
BLOCKS="${2:-3}"
STEPS="${3:-200}"
ARM_SEQ="${ARM_SEQ:-w0 w2 w4 w8 w16 t0 t2 t4 t8 t16 t16 t8 t4 t2 t0 w16 w8 w4 w2 w0}"
mkdir -p "${OUTDIR}"

run_arm() {
  local arm="$1" tag="$2" mode inserts
  case "${arm:0:1}" in
    w) mode=wide ;;
    t) mode=tiny ;;
    *) echo "unknown arm ${arm}" >&2; return 1 ;;
  esac
  inserts="${arm:1}"
  echo "=== $(date -u +%H:%M:%S) ${tag} mode=${mode} inserts=${inserts}"
  DARKBLOOM_R86_MODE="${mode}" \
  DARKBLOOM_R86_INSERTS="${inserts}" \
  python3 research/decode_probe.py --steps "${STEPS}" \
    --dump-steps "${OUTDIR}/${tag}.steps" \
    --stderr "${OUTDIR}/${tag}.err" \
    > "${OUTDIR}/${tag}.log" 2>&1
  grep -E "^(teacher-forced|decode steps=|prefill)" "${OUTDIR}/${tag}.log"
}

i=0
run_seq() { i=$((i + 1)); run_arm "$1" "$(printf 'b%02d_s%03d_%s' "${blk}" "${i}" "$1")"; }

blk=0
run_seq w0 # discarded warm-up / allocator primer
for ((blk = 1; blk <= BLOCKS; blk++)); do
  for arm in ${ARM_SEQ}; do run_seq "${arm}"; done
done
echo "=== $(date -u +%H:%M:%S) done ${i} runs"
