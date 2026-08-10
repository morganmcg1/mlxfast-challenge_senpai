#!/bin/bash
# R108-N stage 1: paired probe measurement of the candidate instruction removals
# on laguna_sliding_fused_attn_ring_v1.  Each arm is a scratch copy under /tmp;
# the scored surface is untouched, so the stage-1 empty-numstat contract holds.
#
# NULL is the verbatim-copy control and bounds instrument bias.  Residency is
# defeated (FERN_DEFEAT_SLOTS=64) per rule 98.9.
set -u
BIN=${BIN:-/tmp/fernattn}
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=${OUT:-/tmp}
GEN=research/maple-edward-r108n-variant-gen.py
export FERN_LADDER=${FERN_LADDER:-32}
export FERN_ROUNDS=${FERN_ROUNDS:-121}
export FERN_REPS=${FERN_REPS:-200}
export FERN_DEFEAT_SLOTS=${FERN_DEFEAT_SLOTS:-64}
ARMS=${ARMS:-"null m1 m2 m3 m1,m2,m3"}

xcrun swiftc -O research/fern_r100_attn_probe.swift -o "$BIN" || exit 1
for arm in ${ARMS}; do
    tag=${arm//,/+}
    cand="${OUT}/lrm-var-${tag}.swift"
    if [ "$arm" = "null" ]; then cp "$SRC" "$cand"
    else python3 "$GEN" "$SRC" "$cand" "$arm" || exit 1; fi
done
for arm in ${ARMS}; do
    tag=${arm//,/+}
    echo "### variant=${tag} slots=${FERN_DEFEAT_SLOTS} ###"
    log="${OUT}/r108n-var-${tag}.txt"
    "$BIN" "$SRC" "${OUT}/lrm-var-${tag}.swift" > "$log" 2>&1
    echo "exit=$?"
    sed -n '/pipeline properties/,/^$/p;/memory regime/,/^$/p;/paired per-call/,/^$/p' "$log"
done
