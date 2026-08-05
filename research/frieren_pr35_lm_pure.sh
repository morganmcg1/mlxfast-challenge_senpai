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
# ~29 us on each arm mean.
#
# Byte roofline for THIS contrast (B vs stock, measured row counts: 389,120 QKV
# rows/step over 40 layers, 128 groups/row):
#   stock 128 B/row = 49.8 MB/step;  lane-major 65 B/row = 25.3 MB/step
#   => -24.5 MB/step, and at the measured 651.8 GB/s attention rate that is
#      about -37.6 us/step, i.e. ~2.6 sigma against sigma(dT) = +-14.2 us.
# Advisor stop rule: below 30% of that prediction (-11.3 us/step) stop and
# diagnose rather than iterate.
#
# NARROW_LOG=1 in BOTH arms (symmetric, init-time only) so the .err files carry
# the reachability proof: OFF must show "inactive: qkv" and ON must show
# "built lane-major: qkv". A screen whose ON arm did not build the bank measures
# nothing.
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."
steps="${STEPS:-512}"

run() {
    local name="$1"
    shift
    echo "=== LM PURE ${name} t=$(date -u +%H:%M:%S) ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_ATTN_SCALE_NARROW=0 \
        DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 "$@" \
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
