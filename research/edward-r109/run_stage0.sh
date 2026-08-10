#!/bin/bash
# R109-D stage 0b sweep: free ceiling and substitute pricing for the sliding
# kernel QK reduction, at the scored geometry only (K=32 threadgroups).
#
# Two NULL controls bracket the candidate arms so the instrument's own bias is
# measured under the same thermal conditions as the verdict it qualifies.
set -u
cd "$(dirname "$0")/../.." || exit 1
export FERN_ROUNDS="${FERN_ROUNDS:-101}"
export FERN_REPS="${FERN_REPS:-200}"

for slots in 64 1; do
  i=0
  for arm in null qk_free qk_ladder2 qk_quad_bcast null; do
    i=$((i + 1))
    bash research/edward-r109/run_probe.sh "$arm" "$slots" "_$i" \
      | grep -E "^ +32 +1\.60" \
      | sed "s/^/[$i $arm slots=$slots] /"
  done
done
