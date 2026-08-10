#!/bin/bash
# R109-D stage 0d: price the padding an M=2 MMA tile pays for the QK product.
#
# An 8x8x8 simdgroup MMA can only fill 2 of its 8 M rows with real queries, so
# the MMA arm executes 4x the useful MACs. These arms pay that bill on the
# scalar pipeline, which is the honest MMA stand-in whenever an MMA MAC costs
# what a scalar FMA MAC costs.
#
#   qk_fma4x          16 QK products + simd_sum        padding cost alone
#   qk_fma4x_bcast0   16 QK products + simd_shuffle(0) padding cost + MMA epilogue
#
# qk_fma4x_bcast0 is the decision arm: if it is not faster than base, an
# MMA-shaped QK tile cannot win at MAC-rate parity.
set -u
cd "$(dirname "$0")/../.." || exit 1
export FERN_ROUNDS="${FERN_ROUNDS:-101}"
export FERN_REPS="${FERN_REPS:-200}"

for slots in 64 1; do
  i=0
  for arm in null qk_fma4x_bcast0 qk_fma4x qk_bcast0 null; do
    i=$((i + 1))
    bash research/edward-r109/run_probe.sh "$arm" "$slots" "_d$i" \
      | grep -E "^ +32 +1\.60" \
      | sed "s/^/[d$i $arm slots=$slots] /"
  done
done
