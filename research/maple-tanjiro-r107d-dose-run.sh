#!/bin/bash
# R107-D stage 1(b) driver: instruction-count dose curve on the fused decode
# attention kernels via fern's cache-defeat attention probe.
#
# Arm d=0 is the A/B NULL control (base against a verbatim copy), so the
# instrument bias floor is measured with the same code path as the dosed arms.
#
# TAG=sliding  (default) laguna_sliding_fused_attn_ring_v1, 4-deep loop
# TAG=full ANCHOR_LO=2100 ANCHOR_HI=2200 ITERS=8
#   FERN_KERNEL=laguna_full_fused_attn_grow_v1 FERN_GQA=6 FERN_ITER_POSITIONS=64
set -u
BIN=${BIN:-/tmp/fernattn}
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=${OUT:-/tmp}
TAG=${TAG:-sliding}
ANCHOR_LO=${ANCHOR_LO:-1600}
ANCHOR_HI=${ANCHOR_HI:-1720}
ITERS=${ITERS:-4}
GUARD=${GUARD:-}
export FERN_LADDER=${FERN_LADDER:-32}
export FERN_ROUNDS=${FERN_ROUNDS:-41}
export FERN_REPS=${FERN_REPS:-200}
export FERN_DEFEAT_SLOTS=${FERN_DEFEAT_SLOTS:-64}
DOSES=${DOSES:-"0 4 16"}
for d in ${DOSES}; do
    bash research/maple-tanjiro-r107d-dose-gen.sh "$SRC" "$d" \
        "${OUT}/lrm-${TAG}-dose${d}.swift" "$ANCHOR_LO" "$ANCHOR_HI" "$ITERS" "$GUARD" || exit 1
done
for d in ${DOSES}; do
    echo "### ${TAG} kernel=${FERN_KERNEL:-laguna_sliding_fused_attn_ring_v1} slots=${FERN_DEFEAT_SLOTS} dose ${d} ###"
    log="${OUT}/stage1b-${TAG}-s${FERN_DEFEAT_SLOTS}-dose${d}.txt"
    "$BIN" "$SRC" "${OUT}/lrm-${TAG}-dose${d}.swift" > "$log" 2>&1
    echo "exit=$?"
    sed -n '/pipeline properties/,/^$/p;/memory regime/,/^$/p;/paired per-call/,/^$/p' "$log"
done
