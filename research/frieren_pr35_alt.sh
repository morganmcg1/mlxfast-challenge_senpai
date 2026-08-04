#!/usr/bin/env bash
# PR35 narrow attention scale planes: in-process parity A/B.
#
# DARKBLOOM_SCALE_ALTERNATE=1 makes even model invocations read the narrow
# planes and odd invocations the stock plane, so both arms are timed inside one
# worker process. The seed forward is invocation 1, so decode step index 0, 2,
# 4 ... are the narrow arm.
#
# Arms (q/k/v only unless stated); the two research arms are deliberately not
# numerically correct and only separate scale bytes from scale load count:
#   narrow  21 B/32 groups, 3 scale loads per group      (the mechanism)
#   nibble  16 B/32 groups, 1 scale load per group       (bytes only)
#   dummy   32 B/32 groups, 3 scale loads per group      (loads only)
#   oproj   the mechanism on o_proj instead of q/k/v
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."
steps="${STEPS:-512}"

run() {
    local name="$1"
    shift
    echo "=== ALT ${name} ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_SCALE_ALTERNATE=1 "$@" \
        python3 research/decode_probe.py --steps "${steps}" \
        --dump-steps "/tmp/pr35_alt_${name}.txt" \
        --stderr "/tmp/pr35_alt_${name}.err" 2>&1 |
        grep -E "decode steps|divergences|diagnostics after decode"
    grep -h -E "narrow-scales|scale-alternate" "/tmp/pr35_alt_${name}.err" | sort -u
    python3 research/frieren_pr35_alt_stats.py "/tmp/pr35_alt_${name}.txt"
}

run narrow DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0
run nibble DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0 DARKBLOOM_SCALE_MICRO_ARM=nibble
run dummy DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0 DARKBLOOM_SCALE_MICRO_ARM=dummy
run oproj DARKBLOOM_ATTN_SCALE_NARROW_QKV=0
run narrow2 DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0
