#!/usr/bin/env bash
# PR35 deliverable B, screen 2: the FULL CANDIDATE STACK against all-stock.
#
# Screen 1 (research/frieren_pr35_lm_pure.sh) isolates the lane-major QKV plane
# with o_proj on the stock plane in both arms. That is the right contrast for
# causal attribution of B, but it deliberately under-measures the candidate:
# with no environment overrides the branch ships BOTH the lane-major QKV plane
# AND the R1 narrow o_proj plane.
#
#   STACK : (no overrides)  -> lane-major QKV + R1 narrow o_proj
#   STOCK : DARKBLOOM_ATTN_SCALE_NARROW=0 DARKBLOOM_ATTN_SCALE_LANEMAJOR=0
#
# DARKBLOOM_ATTN_SCALE_NARROW=0 is the master gate for the R1 narrow banks
# (QKV and o_proj); DARKBLOOM_ATTN_SCALE_LANEMAJOR=0 gates the lane-major bank
# independently. Confirmed empirically from the screen-1 .err logs: the STOCK
# arm prints "inactive: qkv h48/h64" and "inactive: oproj h48/h64".
#
# Why this screen matters for a decision, not just for a number:
#   * STACK - STOCK is what a ranked receipt would actually show.
#   * (STACK - STOCK) - (B - STOCK) isolates the R1 narrow o_proj contribution,
#     which is exactly what the byte-budget-driven R1 strip would DELETE. The
#     strip is therefore not free, and this screen prices it.
#
# Byte roofline: B alone -24.5 MB/step (~ -37.6 us/step at 651.8 GB/s).
# R1 narrow o_proj is roughly 241 B/row against 384/512 stock over 81,920
# rows/step, order -12 MB/step, so the stack should land near -37 MB/step.
#
# Same ABBA-per-round structure and the same symmetric dispatch log as screen 1.
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."
steps="${STEPS:-512}"

run() {
    local name="$1"
    shift
    echo "=== LM STACK ${name} t=$(date -u +%H:%M:%S) ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 "$@" \
        python3 research/decode_probe.py --steps "${steps}" \
        --dump-steps "/tmp/pr35_lm_stack_${name}.txt" \
        --stderr "/tmp/pr35_lm_stack_${name}.err" 2>&1 |
        grep -E "decode steps|divergences|peak_ram"
}

stock=(DARKBLOOM_ATTN_SCALE_NARROW=0 DARKBLOOM_ATTN_SCALE_LANEMAJOR=0)

for round in 1 2 3; do
    run "on_r${round}"
    run "off_r${round}" "${stock[@]}"
    run "off_s${round}" "${stock[@]}"
    run "on_s${round}"
done
