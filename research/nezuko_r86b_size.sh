#!/usr/bin/env bash
# Research-only R86-B boundary-price size sweep (pre-registered CP-1).
#
#   research/nezuko_r86b_size.sh /tmp/r86b/size [BLOCKS] [STEPS]
#
# Same dependent chain as the TINY arm, with the scratch width swept. Arms are
# `z<width_elems>_<inserts>`; width is in BF16 elements, so bytes = 2*width.
# Each width is measured at inserts 0 and 2 (k = 0 and k = 80 boundaries), and
# price(W) = (T(2) - T(0)) / 80. The fold is present at both rungs, so it
# cancels in the difference.
#
# Separates the fixed boundary term from the byte term:
#   price(W) = c_fixed + 2W / BW_eff
set -uo pipefail
OUTDIR="${1:?outdir}"
BLOCKS="${2:-2}"
STEPS="${3:-200}"
# 2 B, 64 B, 4 KiB, 64 KiB, 4 MiB
WIDTHS="${WIDTHS:-1 32 2048 32768 2097152}"
mkdir -p "${OUTDIR}"

run_arm() {
  local width="$1" inserts="$2" tag="$3"
  echo "=== $(date -u +%H:%M:%S) ${tag} width=${width} bytes=$((2 * width)) inserts=${inserts}"
  DARKBLOOM_R86_MODE=size \
  DARKBLOOM_R86_WIDTH="${width}" \
  DARKBLOOM_R86_INSERTS="${inserts}" \
  python3 research/decode_probe.py --steps "${STEPS}" \
    --dump-steps "${OUTDIR}/${tag}.steps" \
    --stderr "${OUTDIR}/${tag}.err" \
    > "${OUTDIR}/${tag}.log" 2>&1
  grep -E "^(teacher-forced|decode steps=)" "${OUTDIR}/${tag}.log"
}

i=0
run_seq() {
  i=$((i + 1))
  run_arm "$1" "$2" "$(printf 'b%02d_s%03d_z%s_%s' "${blk}" "${i}" "$1" "$2")"
}

blk=0
run_seq 1 0 # discarded warm-up / allocator primer
for ((blk = 1; blk <= BLOCKS; blk++)); do
  # Forward pass: 0 then 2 for each width; reverse pass mirrors it, so the
  # paired difference for every width sits symmetrically inside the block.
  for w in ${WIDTHS}; do run_seq "${w}" 0; run_seq "${w}" 2; done
  for w in $(echo ${WIDTHS} | tr ' ' '\n' | tail -r | tr '\n' ' '); do
    run_seq "${w}" 2; run_seq "${w}" 0
  done
done
echo "=== $(date -u +%H:%M:%S) done ${i} runs"
