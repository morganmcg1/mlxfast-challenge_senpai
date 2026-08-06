#!/usr/bin/env bash
# PR35 narrow attention scale planes: pure-configuration replicate screen.
#
# The in-process parity instrument resolves the mechanism at 10 sigma but only
# ever runs alternating arms. This screen runs the shipped configuration (all
# steps narrow) against the kill switch, six replicates each, alternating so a
# monotone drift cancels. Per-pass median spread on this host is ~70 us, so six
# replicates give ~29 us on each arm mean against a predicted -95 us.
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."
steps="${STEPS:-512}"

run() {
    local name="$1"
    shift
    echo "=== PURE ${name} t=$(date -u +%H:%M:%S) ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full "$@" \
        python3 research/decode_probe.py --steps "${steps}" \
        --dump-steps "/tmp/pr35_pure_${name}.txt" \
        --stderr "/tmp/pr35_pure_${name}.err" 2>&1 |
        grep -E "decode steps|divergences"
}

for round in 1 2 3; do
    run "on_r${round}"
    run "off_r${round}" DARKBLOOM_ATTN_SCALE_NARROW=0
    run "off_s${round}" DARKBLOOM_ATTN_SCALE_NARROW=0
    run "on_s${round}"
done
