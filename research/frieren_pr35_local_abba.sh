#!/usr/bin/env bash
# PR35 narrow attention scale planes: matched local-iterate ABBA.
#
# Four full local-iterate passes in ON OFF OFF ON order so a monotone host
# drift cancels in each arm's mean. Every pass runs the same binary and the
# same official baseline constants; only DARKBLOOM_ATTN_SCALE_NARROW changes.
# Local prefill on this M4 Pro is not comparable to the official runner and is
# read only as a no-regression check.
# Research-only; not part of the submission surface.
set -u
cd "$(dirname "$0")/.."

pass() {
    local name="$1"
    shift
    local log="/tmp/pr35_abba_${name}.log"
    echo "=== PASS ${name} t=$(date -u +%H:%M:%S) ==="
    env "$@" research/run_local_benchmark.sh --local-iterate >"${log}" 2>&1
    echo "exit=$?"
    grep -E "summary|decode_speedup|prefill_speedup|est_score|FAIL|failed|mismatch|WARNING" \
        "${log}" | tail -14
    grep -h "narrow-scales" "${log}" | sort -u
}

pass on1 DARKBLOOM_ATTN_SCALE_NARROW=1
pass off1 DARKBLOOM_ATTN_SCALE_NARROW=0
pass off2 DARKBLOOM_ATTN_SCALE_NARROW=0
pass on2 DARKBLOOM_ATTN_SCALE_NARROW=1
