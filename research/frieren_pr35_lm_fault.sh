#!/usr/bin/env bash
# PR35 deliverable B power control: prove the correctness harness can see a
# lane-permutation misread of the 4-bit lane-major QKV scale plane.
#
# The reconstruction certificate is structurally blind to the kernel's
# addressing: it only checks builder^-1 . builder == id on the bank data, so a
# kernel that reads the RIGHT bank at the WRONG lane offset passes it. This
# arm injects exactly that class of bug with a temporary DARKBLOOM_LM_FAULT
# hook (research/frieren-pr35-lanemajor-fault.patch) that makes every lane read
# its neighbour's packed ushort: `+ simd_lid` -> `+ (simd_lid ^ 1u)`.
#
# Why this fault and not another: it keeps the ushort alignment legal, leaves
# the 0xFF escape arm untouched, cannot be constant-folded, and fires on
# 98.1-99.6% of rows in every NVFP4 QKV layer. A row only no-ops when its two
# neighbouring lanes happen to carry identical nibble pairs.
#
# PASS = fault arm reports > 0 divergences AND control arm reports 0 on the
# same binary. Both arms must log a lane-major dispatch, otherwise the fault
# was never reachable and the result is void.
set -u
cd "$(dirname "$0")/.."

echo "=== FAULT arm (DARKBLOOM_LM_FAULT=1; must diverge) ==="
env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_LM_FAULT=1 \
    DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
    python3 research/decode_probe.py --steps 32 \
    --stderr /tmp/pr35_lm_fault.err 2>&1 | grep -E "decode steps|divergences|peak_ram"
sort -u /tmp/pr35_lm_fault.err | grep "narrow-scales"

echo "=== CONTROL arm (same binary, no fault; must be 0 divergences) ==="
env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
    DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
    python3 research/decode_probe.py --steps 32 \
    --stderr /tmp/pr35_lm_control.err 2>&1 | grep -E "decode steps|divergences|peak_ram"
sort -u /tmp/pr35_lm_control.err | grep "narrow-scales"
