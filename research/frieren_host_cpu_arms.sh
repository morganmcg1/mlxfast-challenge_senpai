#!/bin/bash
# Sequential host-CPU probe arms for the steady one-token decode step.
# One model-holding process at a time; each arm loads the model fresh.
# Usage: research/frieren_host_cpu_arms.sh [label-prefix] [spin-us-list] [head-spin-us-list]
set -u
cd "$(dirname "$0")/.." || exit 1

PREFIX="${1:-base}"
SPINS="${2:-0}"
HEAD_SPINS="${3:-}"

run_arm() {
    local label="$1" spin="$2" head="$3"
    echo "=== arm ${label} spin=${spin} head=${head} ==="
    env DARKBLOOM_DECODE_HOST_CPU=1 \
        DARKBLOOM_DECODE_HOST_SPIN_US="${spin}" \
        DARKBLOOM_DECODE_HOST_SPIN_HEAD_US="${head}" \
        python3 research/frieren_host_cpu_probe.py \
        --label "${label}" --warmup-steps 100 --measure-steps 400
}

for spin in ${SPINS}; do
    run_arm "${PREFIX}-spin${spin}" "${spin}" 0
done

for head in ${HEAD_SPINS}; do
    run_arm "${PREFIX}-head${head}" 0 "${head}"
done
