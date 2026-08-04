#!/bin/bash
# Surgical test of the "first commit" mechanism behind the MLX_MAX_MB_PER_BUFFER
# effect, at ranked-parity startup settings.
#
# CommandEncoder::needs_commit() is (buffer_sizes_ >> 20) > max_mb with
# buffer_sizes_ counted in ELEMENTS (device.cpp:562, :396-399). The bf16
# embedding table is 100352 x 2048 = 205 520 896 elements, i.e. 196 when shifted
# right by 20. So the very first set_input_array of a decode step trips the cut
# iff max_mb <= 195:
#   max_mb = 195 -> 196 > 195 -> commit immediately after the embedding op
#   max_mb = 196 -> 196 > 196 -> false -> the first command buffer keeps growing
# Everything else about the two configurations is identical. A step-time jump
# across that one-unit boundary isolates "how early the first command buffer is
# committed" from "how many interior command-buffer boundaries there are".
#
# Part 2 also traces the command-buffer structure at max_mb = 50 (best value in
# research/frieren_cb_mb_sweep.sh) and at the ranked 200, so the first-commit
# offset and the interior boundary count can be read directly.
set -u
cd "$(dirname "$0")/.." || exit 1

STEPS="${STEPS:-2000}"
WARMUP="${WARMUP:-200}"

arm() {
    local label="$1" mb="$2" stage="$3"
    echo "=== arm ${label} mb=${mb} stage=${stage} ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=400 \
        DARKBLOOM_DECODE_ASYNC_STAGE="${stage}" \
        python3 research/frieren_host_cpu_probe.py \
        --label "${label}" \
        --warmup-steps "${WARMUP}" --measure-steps "${STEPS}"
}

DEFAULT_STAGE="at:0,1,7,15,23,31,39"

echo "##### part 1: threshold crossing and schedule interaction #####"
# 196 vs 195 crosses the embedding-charge boundary and nothing else, isolating
# "how early the first command buffer is committed". ladder1 fires asyncEval
# after every one of the 40 layers (decode only, `isSingleTokenDecode` guard at
# LagunaRuntimeModel.swift:10768), so it is the finest boundary schedule
# reachable at LAYER granularity. If mb=50 still beats mb=200 under ladder1, the
# remaining win is SUB-layer and no layer schedule can reach it.
for round in 1 2; do
    arm "T${round}-mb200-default" 200 "${DEFAULT_STAGE}"
    arm "T${round}-mb196-default" 196 "${DEFAULT_STAGE}"
    arm "T${round}-mb195-default" 195 "${DEFAULT_STAGE}"
    arm "T${round}-mb50-default" 50 "${DEFAULT_STAGE}"
    arm "T${round}-mb200-ladder1" 200 "ladder1"
    arm "T${round}-mb50-ladder1" 50 "ladder1"
done

echo "##### part 2: command-buffer structure traces #####"
for mb in 50 200; do
    raw="/tmp/frieren_cbprof_full_mb${mb}.txt"
    echo "=== trace full-mb${mb} ==="
    env FRIEREN_CBPROF=1 DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=400 \
        python3 research/frieren_host_cpu_probe.py \
        --label "trace-mb${mb}" --warmup-steps 60 --measure-steps 300 \
        2>"${raw}"
    echo "--- analysis full-mb${mb} ---"
    python3 research/frieren_head_region.py "${raw}"
done
