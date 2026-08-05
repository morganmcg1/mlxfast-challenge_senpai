#!/usr/bin/env bash
# PR35 deliverable B: pure-configuration replicate screen, lane-major QKV scale
# plane vs the STOCK plane.
#
# Exactly one environment variable differs between the arms:
#
#   ON  : DARKBLOOM_ATTN_SCALE_NARROW=0                                (QKV lane-major)
#   OFF : DARKBLOOM_ATTN_SCALE_NARROW=0 DARKBLOOM_ATTN_SCALE_LANEMAJOR=0 (QKV stock)
#
# NARROW=0 in BOTH arms so the R1 bank can never be the fallback and o_proj is
# on the stock plane in both. The contrast is therefore B vs stock on the QKV
# site alone, which is what the advisor asked for -- B vs R1 would confound two
# narrowing schemes.
#
# Three rounds of ON/OFF/OFF/ON so a monotone host drift cancels within each
# round. Per-pass median spread on this host is ~70 us, so six replicates give
# ~29 us on each arm mean; the advisor's receipt-resolvability floor is ~43
# us/step and the byte roofline for this arm predicts about -19 us/step, so this
# screen is expected to be directional only.
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."
steps="${STEPS:-512}"

run() {
    local name="$1"
    shift
    echo "=== LM PURE ${name} t=$(date -u +%H:%M:%S) ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_ATTN_SCALE_NARROW=0 "$@" \
        python3 research/decode_probe.py --steps "${steps}" \
        --dump-steps "/tmp/pr35_lm_pure_${name}.txt" \
        --stderr "/tmp/pr35_lm_pure_${name}.err" 2>&1 |
        grep -E "decode steps|divergences|peak_ram"
}

for round in 1 2 3; do
    run "on_r${round}"
    run "off_r${round}" DARKBLOOM_ATTN_SCALE_LANEMAJOR=0
    run "off_s${round}" DARKBLOOM_ATTN_SCALE_LANEMAJOR=0
    run "on_s${round}"
done
