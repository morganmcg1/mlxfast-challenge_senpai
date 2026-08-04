#!/bin/bash
# Env-only screen of the command-buffer-count hypothesis for the decode step.
#
# The head-region instrumentation showed ~78 command buffers per steady decode
# step and ~114 us/step of GPU idle concentrated at command-buffer boundaries.
# MLX cuts a command buffer every max_ops_per_buffer_ ops or max_mb_per_buffer_
# megabytes of inputs (Vendor/mlx-swift/.../backend/metal/device.cpp), and both
# limits are overridable with MLX_MAX_OPS_PER_BUFFER / MLX_MAX_MB_PER_BUFFER
# (Vendor/mlx-swift/Source/Cmlx/mlx/mlx/utils.h). This screen raises the limits
# through the environment only -- no code change -- and compares parent-side
# wall ms/step in one thermal window.
#
# Arms are interleaved (A B C A2 B2 C2) so host drift shows up as A-vs-A2.
set -u
cd "$(dirname "$0")/.." || exit 1

STEPS="${STEPS:-400}"
WARMUP="${WARMUP:-100}"

run_arm() {
    local label="$1"; shift
    echo "=== arm ${label}: $* ==="
    env "$@" python3 research/frieren_host_cpu_probe.py \
        --label "${label}" --warmup-steps "${WARMUP}" --measure-steps "${STEPS}"
}

for round in 1 2; do
    run_arm "A${round}-default" MLXFAST_UNUSED=0
    run_arm "B${round}-ops4096-mb4096" MLX_MAX_OPS_PER_BUFFER=4096 MLX_MAX_MB_PER_BUFFER=4096
    run_arm "C${round}-mb4096" MLX_MAX_MB_PER_BUFFER=4096
done
