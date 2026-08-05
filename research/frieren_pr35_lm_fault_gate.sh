#!/usr/bin/env bash
# PR35 deliverable B power control, tier 3: fault-inject the SHIPPING
# correctness gate.
#
# Why this exists. Two instruments have now been shown blind to a lane-major
# scale *addressing* fault:
#
#   1. The greedy teacher-forced probe (research/frieren_pr35_lm_fault.sh).
#      Modes 5/6/1 gave 0 divergences at 128 steps. Only catastrophic faults
#      (code -> 0) move an argmax.
#   2. The upstream-equivalence oracle (research/frieren_pr35_lm_fault_oracle.sh).
#      Even CATASTROPHIC mode 3 left it at a perfect 8/8 with byte-identical
#      logits, and no dispatch-log line appeared. Reason: the oracle builds the
#      model with LagunaRuntimeModel(config) + update() + eval()
#      (LagunaUpstreamEquivalence.swift:74-88) and never calls
#      prepareFusedRuntimeWeights(), whose ONLY caller is
#      LagunaRuntimeWeights.swift:637. So _nativeAffineQKV is nil, the r1 /
#      lane-major dispatch is not even reached, and decode falls back to the
#      BF16 fused norm+QKV projection. Documented independently at
#      research/CURRENT_RESEARCH_STATE.md:832.
#
# That leaves exactly one instrument that provably reaches the bank: the golden
# correctness gate, which runs through LagunaRuntimeWeightCache and therefore
# does build and dispatch it. --local-submit uses the 1024-step golden
# (public_longcopy_gate_english_512_1024.json) for checked_steps 1025, which is
# 8x the greedy probe's 128 steps.
#
# READOUT: passed / max_abs_diff / checked_steps.
# PASS = the fault arm reports passed:false or max_abs_diff != 0.
# FAIL = the fault arm still passes, in which case NO available instrument can
#        see a lane-major addressing error and B needs a kernel-level
#        self-certificate instead of an external probe.
set -u
cd "$(dirname "$0")/.."

mode="${MODE:-5}"
log="/tmp/pr35_lm_fault_gate_${mode}.txt"
echo "=== SHIPPING GATE with DARKBLOOM_LM_FAULT=${mode} (1024-step golden) ==="
env DARKBLOOM_LM_FAULT="${mode}" ./benchmark.sh --local-submit >"${log}" 2>&1
echo "benchmark.sh exit=$?"
grep -nE 'passed|max_abs_diff|checked_steps|golden_hash|peak_ram_gb|first_failing|divergen|actual_token|expected_token|case_count|error' "${log}" \
    | head -40
echo "--- full log at ${log} ---"
