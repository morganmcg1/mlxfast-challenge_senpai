#!/bin/bash
# Sequential host-CPU probe arms for the steady one-token decode step.
# One model-holding process at a time; each arm loads the model fresh.
# Usage: research/frieren_host_cpu_arms.sh [label-prefix] [spin-us-list]
set -u
cd "$(dirname "$0")/.." || exit 1

PREFIX="${1:-base}"
SPINS="${2:-0}"

for spin in ${SPINS}; do
    echo "=== arm ${PREFIX} spin=${spin} ==="
    env DARKBLOOM_DECODE_HOST_CPU=1 DARKBLOOM_DECODE_HOST_SPIN_US="${spin}" \
        python3 research/frieren_host_cpu_probe.py \
        --label "${PREFIX}-spin${spin}" --warmup-steps 100 --measure-steps 400
done
