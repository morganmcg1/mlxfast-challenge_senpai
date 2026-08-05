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
#   5 - the four K-block codes inside a lane's word are reversed
#   6 - every lane reads the word 16 lanes away (`(simd_lid + 16) & 31`)
#
# Round 1 (modes 3/4/2/0, 32 steps) established that both arms are live:
# 3 -> 32 divergences, 4 -> 2 divergences, 2 -> 1 divergence, control -> 0.
# Mode 2 perturbs 100% of fitting codes yet moves only one argmax, because
# +1 on the code is a near-uniform +8.3% on every Q/K/V scale. That fixes the
# probe's sensitivity floor and explains mode 1's silence: an `xor 1` lane swap
# exchanges the codes of groups L and L+1, i.e. columns 16 apart, which the
# census shows usually carry the same code.
#
# Round 2 (this configuration) uses the addressing permutations that move a
# code across columns 512 apart, where no such correlation exists.
#
# PASS = the chosen fault arm reports > 0 divergences AND the control arm
# reports 0 on the same binary. Every arm must log a lane-major dispatch,
# otherwise the fault was never reachable and the result is void.
set -u
cd "$(dirname "$0")/.."

STEPS="${STEPS:-128}"

run_arm() {
    local label="$1" mode="$2"
    echo "=== ${label} (DARKBLOOM_LM_FAULT=${mode}, steps=${STEPS}) ==="
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_LM_FAULT="${mode}" \
        DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
        python3 research/decode_probe.py --steps "${STEPS}" \
        --stderr "/tmp/pr35_lm_f${mode}.err" 2>&1 \
        | grep -E "decode steps|divergences|peak_ram"
    sort -u "/tmp/pr35_lm_f${mode}.err" \
        | grep -E "narrow-scales (active|inactive|lane-major|built)"
}

run_arm "MODE 5 reverse the four K-block codes in each lane word" 5
run_arm "MODE 6 read the lane word 16 lanes away" 6
run_arm "MODE 1 read the neighbour lane word (xor 1)" 1
run_arm "CONTROL same binary, no fault (must be 0 divergences)" 0
