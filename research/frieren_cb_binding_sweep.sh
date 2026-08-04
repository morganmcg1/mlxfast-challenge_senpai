#!/usr/bin/env bash
# Which of MLX's two command-buffer commit limits binds on the steady decode
# step? Counting only, no timing: each arm traces 300 steady steps at ranked
# parity (DARKBLOOM_STARTUP_MEMORY_PROFILE=full) and reports cb/step plus the
# ops-per-committed-buffer distribution.
#
# Arm 1/2 hold the byte cap at the shipped 200 MiB and move ops 200 -> 400.
# Arms 3-6 hold ops at the shipped 200 and move the byte cap 40/100/200/400.
#
# Research-only; requires the FRIEREN_CBPROF instrumentation in the worktree.
set -uo pipefail

cd "$(dirname "$0")/.."

arm() {
    local label="$1" mb="$2" ops="$3"
    local raw="/tmp/frieren_cbbind_${label}.txt"
    echo "=== arm ${label}: MLX_MAX_MB_PER_BUFFER=${mb} MLX_MAX_OPS_PER_BUFFER=${ops} ==="
    env FRIEREN_CBPROF=1 \
        DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER="${mb}" \
        MLX_MAX_OPS_PER_BUFFER="${ops}" \
        python3 research/frieren_host_cpu_probe.py \
        --label "${label}" --warmup-steps 60 --measure-steps 300 2>"${raw}"
    python3 research/frieren_cb_binding.py "${raw}" \
        --label "${label}" --max-mb "${mb}" --max-ops "${ops}"
    echo
}

# Shipped configuration, reached through the in-tree default rather than the
# environment, so the ranked path itself is measured at least once.
raw="/tmp/frieren_cbbind_shipped.txt"
echo "=== arm shipped: no MLX_MAX_* in env, in-tree default applies ==="
env FRIEREN_CBPROF=1 DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
    python3 research/frieren_host_cpu_probe.py \
    --label shipped --warmup-steps 60 --measure-steps 300 2>"${raw}"
python3 research/frieren_cb_binding.py "${raw}" --label shipped --max-mb 200 --max-ops 200
echo

arm ops200 200 200
arm ops400 200 400
arm mb40 40 200
arm mb100 100 200
arm mb400 400 200
