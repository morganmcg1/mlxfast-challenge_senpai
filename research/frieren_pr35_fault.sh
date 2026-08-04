#!/usr/bin/env bash
# PR35: prove the init-time reconstruction certificate is a live safety net.
#
# Ran against a worker built with a temporary DARKBLOOM_SCALE_FAULT hook (commit
# 48d28a2, removed again in the next commit) that flipped one bit of every
# nibble plane before the certificate. Observed: all 80 banks logged
# `declined (reconstruction mismatch)`, all four dispatch shapes logged
# `inactive`, and the greedy tokens still matched -- the certificate is a live
# safety net and the wide fallback is exact. Re-adding the hook is the only way
# to run this again. Research-only; not part of the submission surface.
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
