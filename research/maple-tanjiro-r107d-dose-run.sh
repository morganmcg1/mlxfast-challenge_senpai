#!/bin/bash
# R107-D stage 1(b) driver: instruction-count dose curve on
# laguna_sliding_fused_attn_ring_v1 via fern's cache-defeat attention probe.
#
# Arm d=0 is the A/B NULL control (base against a verbatim copy), so the
# instrument bias floor is measured with the same code path as the dosed arms.
set -u
BIN=${BIN:-/tmp/fernattn}
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=${OUT:-/tmp}
export FERN_LADDER=${FERN_LADDER:-32}
export FERN_ROUNDS=${FERN_ROUNDS:-41}
export FERN_REPS=${FERN_REPS:-200}
export FERN_DEFEAT_SLOTS=${FERN_DEFEAT_SLOTS:-64}
DOSES=${DOSES:-"0 4 16"}
for d in ${DOSES}; do
    bash research/maple-tanjiro-r107d-dose-gen.sh "$SRC" "$d" "${OUT}/lrm-dose${d}.swift" || exit 1
done
for d in ${DOSES}; do
    echo "### dose ${d} ###"
    "$BIN" "$SRC" "${OUT}/lrm-dose${d}.swift" > "${OUT}/stage1b-dose${d}.txt" 2>&1
    echo "exit=$?"
    sed -n '/pipeline properties/,/^$/p;/paired per-call/,/^$/p' "${OUT}/stage1b-dose${d}.txt"
done
