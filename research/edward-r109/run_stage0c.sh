#!/bin/bash
# R109-D stage 0c: separate the reduction cost from the cross-lane dependency
# cost, and price the correct explicit-shuffle fallback.
#
#   base          simd_sum                      1 cross-lane reduce+broadcast
#   qk_bcast0     simd_shuffle(x, 0)            1 cross-lane broadcast, no reduce
#   qk_ladder5    5-stage shuffle_xor butterfly correct reduce without simd_sum
#   qk_free       nothing                       already measured in stage 0b
#
# qk_bcast0 is also the proxy for the MMA epilogue: an MMA-shaped QK tile still
# has to get each row score from one accumulator lane to all 32 output lanes.
set -u
cd "$(dirname "$0")/../.." || exit 1
export FERN_ROUNDS="${FERN_ROUNDS:-101}"
export FERN_REPS="${FERN_REPS:-200}"

for slots in 64 1; do
  i=0
  for arm in null qk_bcast0 qk_ladder5 qk_free null; do
    i=$((i + 1))
    bash research/edward-r109/run_probe.sh "$arm" "$slots" "_c$i" \
      | grep -E "^ +32 +1\.60" \
      | sed "s/^/[c$i $arm slots=$slots] /"
  done
done
