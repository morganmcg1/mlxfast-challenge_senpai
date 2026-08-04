#!/bin/bash
# Command-buffer-count screen for the steady one-token decode step.
#
# Head-region instrumentation found ~78 command buffers per steady decode step
# on this host and ~114 us/step of GPU idle concentrated at command-buffer
# boundaries. MLX cuts a command buffer when buffer_ops_ > max_ops or
# (buffer_sizes_ >> 20) > max_mb, where buffer_sizes_ counts each distinct input
# buffer's data_size() once per command buffer (elements, not bytes)
# -- Vendor/mlx-swift/.../backend/metal/device.cpp:562.
#
# Both limits come from the environment, and the runtime sets them itself in
# LagunaRuntimeWeights.init:
#   * low-memory profile (<64 GiB): apply() setenv(..., overwrite=1) -> 128/64,
#     so an external MLX_MAX_* value is IGNORED on this host;
#   * full/ranked profile:          setenv(..., overwrite=0)        -> 200/400,
#     so an external MLX_MAX_* value WINS.
# Screening the axis at ranked parity therefore needs the full profile, which
# DARKBLOOM_STARTUP_MEMORY_PROFILE=full selects. On a 48 GiB host that raises
# the allocator cache cap to 32 GiB and wires full residency, so arm 0 is a
# canary: if the full profile cannot run here the rest will fail the same way.
set -u
cd "$(dirname "$0")/.." || exit 1

STEPS="${STEPS:-2000}"
WARMUP="${WARMUP:-200}"

run_arm() {
    local label="$1" steps="$2"; shift 2
    echo "=== arm ${label}: $* ==="
    env "$@" python3 research/frieren_host_cpu_probe.py \
        --label "${label}" --warmup-steps "${WARMUP}" --measure-steps "${steps}"
}

run_arm "canary-full" 200 DARKBLOOM_STARTUP_MEMORY_PROFILE=full || exit 1

for round in 1 2 3; do
    run_arm "F${round}-ranked-200-400" "${STEPS}" \
        DARKBLOOM_STARTUP_MEMORY_PROFILE=full
    run_arm "F${round}-mb4096-ops4096" "${STEPS}" \
        DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER=4096 MLX_MAX_OPS_PER_BUFFER=4096
    run_arm "F${round}-mb50-ops400" "${STEPS}" \
        DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=400
done
