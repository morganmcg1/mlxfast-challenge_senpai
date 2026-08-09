#!/bin/bash
# R100-C Step 1: wrap each arm's router GEMV body in MLX's exact kernel
# signature, compile it, and report where the compiler actually places the four
# `router_weight` device loads relative to the four `threadgroup_barrier`s.
#
# This is the N-B test and needs no GPU time. If arm pf0's emitted code already
# hoists the loads above the first barrier, arms 0 and 1 are the same machine
# code, N-B is confirmed, and the lever closes with no timing work at all.
#
# Run research/maple-nezuko-r100c-dump-msl.sh first to produce the bodies.
set -uo pipefail
cd "$(dirname "$0")/.."

SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
RPG="${RPG:-8}"
OUT=research/msl
mkdir -p "$OUT"

# The router ordinal header, verbatim (precomputed keys are on by default).
awk '/^private let lagunaDecodeRouterOrdinalHeader = """/{f=1; next}
     f&&/^"""$/{exit}
     f' "$SRC" > "$OUT"/r100c_header.metal

emit() {  # $1 = arm tag
    local tag="$1" f="$OUT/r100c_rpg${RPG}_$1.metal"
    {
        echo '#include <metal_stdlib>'
        echo '#include <metal_simdgroup>'
        echo 'using namespace metal;'
        echo 'typedef bfloat bfloat16_t;'
        echo
        cat "$OUT"/r100c_header.metal
        echo
        echo "[[kernel]] void custom_kernel_laguna_residual_rms_router_bf16_2048_rpg${RPG}_keys_v1_${tag}("
        echo '  const device bfloat16_t* residual [[buffer(0)]],'
        echo '  const device bfloat16_t* branch [[buffer(1)]],'
        echo '  const device bfloat16_t* weight [[buffer(2)]],'
        echo '  const device bfloat16_t* router_weight [[buffer(3)]],'
        echo '  const device bfloat16_t* correction_bias [[buffer(4)]],'
        echo '  device bfloat16_t* summed [[buffer(5)]],'
        echo '  device bfloat16_t* normalized [[buffer(6)]],'
        echo '  device bfloat16_t* router_logits [[buffer(7)]],'
        echo '  device uint* router_keys [[buffer(8)]],'
        echo '  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]],'
        echo '  uint3 thread_position_in_threadgroup [[thread_position_in_threadgroup]],'
        echo '  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],'
        echo '  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]]) {'
        cat "$OUT/r100c_rpg${RPG}_$1.body.metal"
        echo '}'
    } > "$f"
    echo "$f"
}

status=0
for tag in pf0 pf1 pf1c; do
    f=$(emit "$tag")
    base="${f%.metal}"
    if ! xcrun -sdk macosx metal -x metal -std=metal3.1 -O3 -c "$f" -o "$base".air 2>"$base".err; then
        echo "FATAL: $tag failed to compile" >&2
        head -20 "$base".err >&2
        status=1
        continue
    fi
    xcrun -sdk macosx metallib "$base".air -o "$base".metallib 2>>"$base".err
    xcrun -sdk macosx metal -x metal -std=metal3.1 -O3 -S "$f" -o "$base".air.ll 2>>"$base".err
    printf '%-5s compiled  air=%s bytes  metallib=%s bytes\n' "$tag" \
        "$(wc -c < "$base".air | tr -d ' ')" \
        "$(wc -c < "$base".metallib 2>/dev/null | tr -d ' ')"
done
exit $status
