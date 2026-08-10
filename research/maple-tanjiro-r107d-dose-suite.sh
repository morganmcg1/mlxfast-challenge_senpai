#!/bin/bash
# R107-D stage 1(b) suite: replication session for the sliding kernel, the
# rule-98.5 cache-resident twin of the same dose curve, and the same dose
# applied to the full-attention kernel.
set -u
export FERN_ROUNDS=${FERN_ROUNDS:-41}
export FERN_REPS=${FERN_REPS:-200}
mkdir -p /tmp/s2 /tmp/s3 /tmp/s4

echo "===== session 2: sliding, cache-defeated ====="
FERN_DEFEAT_SLOTS=64 OUT=/tmp/s2 TAG=sliding \
    bash research/maple-tanjiro-r107d-dose-run.sh

echo "===== rule 98.5 twin: sliding, cache-resident (slots=1) ====="
FERN_DEFEAT_SLOTS=1 OUT=/tmp/s3 TAG=sliding \
    bash research/maple-tanjiro-r107d-dose-run.sh

echo "===== full attention kernel, cache-defeated ====="
FERN_DEFEAT_SLOTS=64 FERN_LADDER=24 FERN_GQA=6 FERN_ITER_POSITIONS=64 \
    FERN_KERNEL=laguna_full_fused_attn_grow_v1 FERN_PARAM_ROWS=1 \
    ANCHOR_LO=2100 ANCHOR_HI=2200 ITERS=8 OUT=/tmp/s4 TAG=full \
    bash research/maple-tanjiro-r107d-dose-run.sh
