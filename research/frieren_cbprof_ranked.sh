#!/bin/bash
# Head-region + command-buffer trace at ranked-parity startup settings.
#
# The <64 GiB low-memory profile force-sets 128 MB / 64 ops command buffers,
# while the ranked 128 GiB box uses 200 MB / 400 ops. DARKBLOOM_STARTUP_MEMORY_
# PROFILE=full selects the ranked settings, and the canary arm of
# frieren_cb_count_arms.sh showed the full profile does run on a 48 GiB host.
# This traces both profiles back to back so the head-region split and the
# command-buffer count can be compared at low vs ranked parity.
set -u
cd "$(dirname "$0")/.." || exit 1

trace_profile() {
    local label="$1"; shift
    local raw="/tmp/frieren_cbprof_${label}.txt"
    echo "=== trace ${label}: $* ==="
    env FRIEREN_CBPROF=1 "$@" \
        python3 research/frieren_host_cpu_probe.py \
        --label "${label}" --warmup-steps 60 --measure-steps 300 2>"${raw}"
    echo "--- analysis ${label} (${raw}) ---"
    python3 research/frieren_head_region.py "${raw}"
}

trace_profile "ranked" DARKBLOOM_STARTUP_MEMORY_PROFILE=full
trace_profile "lowmem" DARKBLOOM_STARTUP_MEMORY_PROFILE=low
