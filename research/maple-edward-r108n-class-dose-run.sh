#!/bin/bash
# R108-N stage 1 driver: price one instruction class per issue slot on the
# sliding fused decode attention kernel, so the census can convert a proposed
# per-thread removal count into microseconds without assuming fma parity.
#
# Arm (mul, d=0) is the A/B NULL control: base against a verbatim copy, so the
# instrument bias floor is measured through the same path as the dosed arms.
# Residency is defeated (FERN_DEFEAT_SLOTS=64) per rule 98.9; a resident number
# would be inflated ~30x.
set -u
BIN=${BIN:-/tmp/fernattn}
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=${OUT:-/tmp}
GEN=research/maple-edward-r108n-class-dose-gen.sh
ITERS=${ITERS:-4}
export FERN_LADDER=${FERN_LADDER:-32}
export FERN_ROUNDS=${FERN_ROUNDS:-41}
export FERN_REPS=${FERN_REPS:-200}
export FERN_DEFEAT_SLOTS=${FERN_DEFEAT_SLOTS:-64}
ARMS=${ARMS:-"fma:4 fma:16 fma:32"}

xcrun swiftc -O research/fern_r100_attn_probe.swift -o "$BIN" || exit 1
echo "probe built: $BIN"
for arm in ${ARMS}; do
    class=${arm%%:*}; d=${arm##*:}
    bash "$GEN" "$SRC" "$d" "${OUT}/lrm-${class}-dose${d}.swift" "$class" \
        1600 1720 "$ITERS" || exit 1
done
for arm in ${ARMS}; do
    class=${arm%%:*}; d=${arm##*:}
    echo "### class=${class} dose=${d} slots=${FERN_DEFEAT_SLOTS} extra_ops_per_thread=$((d * 8 * ITERS)) ###"
    log="${OUT}/r108n-${class}-dose${d}.txt"
    "$BIN" "$SRC" "${OUT}/lrm-${class}-dose${d}.swift" > "$log" 2>&1
    echo "exit=$?"
    sed -n '/pipeline properties/,/^$/p;/memory regime/,/^$/p;/paired per-call/,/^$/p' "$log"
done
