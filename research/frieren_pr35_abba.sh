#!/usr/bin/env bash
# PR35 narrow attention scale planes: position-balanced ABBA per-step timing.
#
#   A = narrow ON  (shipped default: q/k/v + o_proj read the 21 B planes)
#   B = narrow OFF (DARKBLOOM_ATTN_SCALE_NARROW=0, stock 32 B planes)
#
# Positions: p00 discarded warm-up, then A B B A B A A B so each arm's
# positions sum to 18 and balance inside every block of four. The host-CPU
# probe measures a long steady window (default 1200 steps) instead of the
# 256-step decode probe, so the ~1.4% predicted effect is far above noise.
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."

MACMON="${HOME}/bin/macmon"
STEPS="${STEPS:-1200}"

thermal() {
    if [ -x "${MACMON}" ]; then
        "${MACMON}" pipe -s1 2>/dev/null | jq -c \
            '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
    else
        echo "no-macmon"
    fi
}

run_arm() {
    local name="$1" arm="$2"
    echo "=== ${name} arm=${arm} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
    if [ "${arm}" = "A" ]; then
        env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
            python3 research/frieren_host_cpu_probe.py \
            --warmup-steps 60 --measure-steps "${STEPS}" --label "${name}-A"
    else
        env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
            DARKBLOOM_ATTN_SCALE_NARROW=0 \
            python3 research/frieren_host_cpu_probe.py \
            --warmup-steps 60 --measure-steps "${STEPS}" --label "${name}-B"
    fi
}

run_arm p00-discard A
run_arm p01 A
run_arm p02 B
run_arm p03 B
run_arm p04 A
run_arm p05 B
run_arm p06 A
run_arm p07 A
run_arm p08 B
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
