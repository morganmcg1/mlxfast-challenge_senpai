#!/usr/bin/env bash
# Research-only R85-D dispatch-cost ladder driver.
#
#   research/nezuko_r85_ladder.sh /tmp/r85/ladder [BLOCKS] [STEPS]
#
# Arms are `<mode><K>` where mode is the injected-null-dispatch width and K is
# the number of injected ops per decoder layer (40 layers => N_extra = 40*K):
#   w0 w8 w16 w32 w64   wide: chained BF16 multiplies on the [1,1,2048] hidden
#                       stream (4 KiB in + 4 KiB out per injected dispatch)
#   t0 t8 t16 t32 t64   tiny: chained BF16 multiplies on a [1] scalar, folded
#                       back with one broadcast add present at every K
#
# Each block is a palindrome so monotone thermal/allocator drift cancels
# inside the block. w0 is byte-identical to the instrument being disarmed.
set -uo pipefail
OUTDIR="${1:?outdir}"
BLOCKS="${2:-3}"
STEPS="${3:-200}"
ARM_SEQ="${ARM_SEQ:-w0 w8 w16 w32 w64 t0 t8 t16 t32 t64 t64 t32 t16 t8 t0 w64 w32 w16 w8 w0}"
mkdir -p "${OUTDIR}"

run_arm() {
  local arm="$1" tag="$2" mode k
  case "${arm:0:1}" in
    w) mode=wide ;;
    t) mode=tiny ;;
    *) echo "unknown arm ${arm}" >&2; return 1 ;;
  esac
  k="${arm:1}"
  echo "=== $(date -u +%H:%M:%S) ${tag} mode=${mode} k=${k}"
  DARKBLOOM_R85_LADDER_MODE="${mode}" \
  DARKBLOOM_R85_LADDER_K="${k}" \
  python3 research/decode_probe.py --steps "${STEPS}" \
    --dump-steps "${OUTDIR}/${tag}.steps" \
    --stderr "${OUTDIR}/${tag}.err" \
    > "${OUTDIR}/${tag}.log" 2>&1
  grep -E "^(teacher-forced|decode steps=|prefill)" "${OUTDIR}/${tag}.log"
}

i=0
run_seq() { i=$((i + 1)); run_arm "$1" "$(printf 'b%02d_s%03d_%s' "${blk}" "${i}" "$1")"; }

blk=0
run_seq w0   # discarded warm-up / allocator primer
for ((blk = 1; blk <= BLOCKS; blk++)); do
  for arm in ${ARM_SEQ}; do run_seq "${arm}"; done
done
echo "=== $(date -u +%H:%M:%S) done ${i} runs"
