#!/usr/bin/env bash
# PR35: prove the init-time reconstruction certificate is a live safety net.
#
# Run against a worker built with the temporary DARKBLOOM_SCALE_FAULT hook that
# flips one bit of every nibble plane before the certificate runs. Expected:
# every site logs `declined (reconstruction mismatch)`, every dispatch logs
# `inactive` (stock plane), and the greedy tokens still match.
# Research-only; the fault hook is removed again after this run.
set -u
cd "$(dirname "$0")/.."

echo "=== FAULT arm (certificate must decline) ==="
env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_SCALE_FAULT=1 \
    DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
    python3 research/decode_probe.py --steps 32 \
    --stderr /tmp/pr35_fault.err 2>&1 | grep -E "decode steps|divergences"
grep -c "narrow-scales" /tmp/pr35_fault.err
sort -u /tmp/pr35_fault.err | grep "narrow-scales"

echo "=== CONTROL arm (same worker, no fault) ==="
env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
    DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
    python3 research/decode_probe.py --steps 32 \
    --stderr /tmp/pr35_fault_control.err 2>&1 | grep -E "decode steps|divergences"
sort -u /tmp/pr35_fault_control.err | grep "narrow-scales"
