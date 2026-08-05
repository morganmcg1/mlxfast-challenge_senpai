#!/usr/bin/env bash
# PR35 deliverable B power control: prove the correctness harness can see a
# misread of the 4-bit lane-major QKV scale plane.
#
# The reconstruction certificate is structurally blind to the kernel's
# addressing: it only checks builder^-1 . builder == id on the bank data, so a
# kernel that reads the RIGHT bank at the WRONG offset passes it. This script
# injects that class of bug with a temporary DARKBLOOM_LM_FAULT ladder
# (research/frieren-pr35-lanemajor-fault.patch):
#
#   1 - every lane reads its neighbour's packed ushort (`simd_lid ^ 1`)
#   2 - every reconstructed fitting code is biased +1 (fires on every row)
#   3 - every fitting-arm code is forced to 0
#   4 - every escaped-arm code is forced to 0
#
# Mode 1 alone came back silent, which is only possible if the fitting arm is
# not live or if neighbouring lane words agree. 3 and 4 localise which arm the
# dispatch actually takes; 2 is the 100%-fire candidate power control.
#
# PASS = the chosen fault arm reports > 0 divergences AND the control arm
# reports 0 on the same binary. Every arm must log a lane-major dispatch,
# otherwise the fault was never reachable and the result is void.
set -u
cd "$(dirname "$0")/.."

run_arm() {
    local label="$1" mode="$2"
    echo "=== ${label} (DARKBLOOM_LM_FAULT=${mode}) ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_LM_FAULT="${mode}" \
        DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
        python3 research/decode_probe.py --steps 32 \
        --stderr "/tmp/pr35_lm_f${mode}.err" 2>&1 \
        | grep -E "decode steps|divergences|peak_ram"
    sort -u "/tmp/pr35_lm_f${mode}.err" \
        | grep -E "narrow-scales (active|inactive|lane-major|built)"
}

run_arm "MODE 3 zero the fitting arm (must diverge if that arm is live)" 3
run_arm "MODE 4 zero the escape arm (must diverge if that arm is live)" 4
run_arm "MODE 2 bias every fitting code +1 (must diverge)" 2
run_arm "CONTROL same binary, no fault (must be 0 divergences)" 0
