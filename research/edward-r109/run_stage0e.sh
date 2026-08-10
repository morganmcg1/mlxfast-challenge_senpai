#!/bin/bash
# R109-D stage 0e: attribute the arm(c)-minus-DRAM-floor residual.
#
# Arm (c) (qk_loadonly) removes the QK cross-lane reduction and the softmax/PV
# accumulate, leaving loads + QK MACs + loop + epilogue. It still runs far above
# the rule-55 DRAM floor. Two very different causes explain that residual and
# they imply opposite next steps:
#
#   1. load-issue / staging latency        -> a load-geometry retarget could pay
#   2. threadgroup wave quantization       -> geometry, banned this round
#
# The E1 absolute ladder separates them. The scored dispatch is 32 threadgroups
# on 20 cores = 1.60 TG/core, i.e. two waves of 20 + 12. If the residual is wave
# quantization then t(K) is flat from K=20 to K=32 (the second wave is mostly
# idle lanes) and phi(16)=t(32)/t(16) is far below 2. If the kernel is really
# work- or latency-limited per threadgroup then t/K is flat and phi ~ 2.
set -u
cd "$(dirname "$0")/../.." || exit 1
export FERN_LADDER="${FERN_LADDER:-4,8,16,20,32,40,64}"
export FERN_ROUNDS="${FERN_ROUNDS:-31}"
export FERN_REPS="${FERN_REPS:-200}"

for arm in "${@:-null}"; do
  echo "===== arm=$arm ladder=$FERN_LADDER slots=64 ====="
  bash research/edward-r109/run_probe.sh "$arm" 64 "_e" \
    | sed -n '/absolute cost ladder/,/paired per-call/p'
done
