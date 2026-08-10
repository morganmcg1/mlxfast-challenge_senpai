#!/bin/bash
# R109-D stage 0f: does the MMA padding verdict survive the ranked machine's
# occupancy regime?
#
# 18.4 kB of threadgroup memory against a 32 kB/core budget admits exactly one
# resident 1024-thread TG per core, so TG/core is also waves/dispatch. The
# scored 32-TG sliding dispatch is therefore
#
#   20-core M4 Pro : 1.60 TG/core -> two waves (20 + 12)
#   40-core M5 Max : 0.80 TG/core -> one under-filled wave
#
# All stage 0b-0d arms were priced at K=32 on this host, i.e. in the two-wave
# regime the ranked machine never enters. AGENTS.md warns that threadgroup
# geometry can change sign across core counts, so re-price the two decision arms
# at K=16 (0.80 TG/core, the M5 ratio) and K=20 (1.00 TG/core, the boundary).
# K only changes how many head pairs are dispatched; the per-TG kernel, its loads
# and its critical path are identical.
#
#   usage: run_stage0f.sh K [ARMS...]
set -u
cd "$(dirname "$0")/../.." || exit 1
K="${1:?usage: run_stage0f.sh K [ARMS...]}"
shift
ARMS=("$@")
[ ${#ARMS[@]} -gt 0 ] || ARMS=(null qk_bcast0 qk_pad4x qk_pad4x_bcast0 null)

export FERN_LADDER="$K"
export FERN_ROUNDS="${FERN_ROUNDS:-101}"
export FERN_REPS="${FERN_REPS:-200}"

i=0
for arm in "${ARMS[@]}"; do
  i=$((i + 1))
  bash research/edward-r109/run_probe.sh "$arm" 64 "_f${K}_$i" \
    | grep -E "^ +${K} +[0-9]" \
    | sed "s/^/[f$i $arm K=$K] /"
done
