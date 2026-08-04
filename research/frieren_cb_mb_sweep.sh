#!/bin/bash
# Command-buffer referenced-volume threshold sweep at ranked-parity startup.
#
# First screen (research/frieren_cb_count_arms.sh) found, under
# DARKBLOOM_STARTUP_MEMORY_PROFILE=full on this M4 Pro:
#   MLX_MAX_MB_PER_BUFFER=50   -> 8.9625 ms/step (n=2, spread 0.4 us)
#   MLX_MAX_MB_PER_BUFFER=200  -> 9.0717 ms/step (n=3, sd 0.065)  <- ranked default
#   MLX_MAX_MB_PER_BUFFER=4096 -> 9.4158 ms/step (n=2)
# i.e. SMALLER command buffers are faster here, opposite to the direction the
# ranked default was tuned. This sweep maps the curve to find the local optimum
# and whether it is flat or sharp. Rounds are interleaved so host drift shows up
# as a within-value spread.
set -u
cd "$(dirname "$0")/.." || exit 1

STEPS="${STEPS:-2000}"
WARMUP="${WARMUP:-200}"
MBS="${MBS:-8 16 25 50 100 200}"
ROUNDS="${ROUNDS:-1 2}"

for round in ${ROUNDS}; do
    for mb in ${MBS}; do
        echo "=== arm R${round}-mb${mb}-ops400 ==="
        env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
            MLX_MAX_MB_PER_BUFFER="${mb}" \
            MLX_MAX_OPS_PER_BUFFER=400 \
            python3 research/frieren_host_cpu_probe.py \
            --label "R${round}-mb${mb}-ops400" \
            --warmup-steps "${WARMUP}" --measure-steps "${STEPS}"
    done
done
