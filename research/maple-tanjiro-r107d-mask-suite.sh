#!/bin/bash
# R107-D stage 1(c): price instructions issued under a partial-lane mask.
#
# The shipped sliding kernel spends its prologue RoPE section under
# "if (lane < 16)" and its epilogue store under "if (lane == 0)".  Levers P2 and
# P3 in the assignment widen those sections so fewer sequential instructions per
# thread cover the same work.  They can only pay if a masked instruction costs
# the same issue slot as an unmasked one.  This suite injects the identical dose
# unguarded, under "lane < 16", and under "lane == 0", all in one session on the
# defeated cache, and reports the three paired deltas against the same base.
set -u
export OUT=/tmp/s5
mkdir -p "$OUT"
export FERN_DEFEAT_SLOTS=64
export FERN_LADDER=32
export FERN_ROUNDS=41
export FERN_REPS=200

TAG=maskfull  GUARD=""           DOSES="0 4" bash research/maple-tanjiro-r107d-dose-run.sh
TAG=maskhalf  GUARD="lane < 16"  DOSES="4"   bash research/maple-tanjiro-r107d-dose-run.sh
TAG=masklane0 GUARD="lane == 0"  DOSES="4"   bash research/maple-tanjiro-r107d-dose-run.sh
