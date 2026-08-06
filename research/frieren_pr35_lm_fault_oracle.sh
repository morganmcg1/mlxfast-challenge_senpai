#!/usr/bin/env bash
# PR35 deliverable B power control, tier 2: fault-inject the LOGIT-level oracle
# instead of the greedy-token probe.
#
# Why this script exists. The greedy teacher-forced probe turned out to be a
# blunt instrument for this bug class. On one binary, at 32-128 steps:
#
#   mode 3 zero the fitting arm        -> 32/32 divergences
#   mode 4 zero the escape arm         ->  2    divergences
#   mode 2 +1 on every fitting code    ->  1    divergence
#   mode 5 reverse a lane's 4 codes    ->  0    divergences  (128 steps)
#   mode 6 read the word 16 lanes away ->  0    divergences  (128 steps)
#   mode 1 read the neighbour word     ->  0    divergences
#   control                            ->  0    divergences
#
# Only catastrophic faults (code -> 0, i.e. scale -> 0) move an argmax. Every
# *permutation* of a row's own codes is invisible, because a row's codes span
# <= 15 and the distribution is concentrated (top-7 codes ~97.9% of global
# mass), so a permutation exchanges codes that are usually equal or differ by
# +-1 -- and mode 2 shows that even a 100%-coverage +-1 perturbation moves at
# most one argmax in 32 steps. Argmax is simply not sensitive at that scale.
#
# So the greedy probe cannot certify lane-major addressing, and I should not
# claim it does. The instrument that CAN is the upstream-equivalence oracle,
# which reports `maximumAbsoluteLogitError` per step and which V2 already shows
# is exactly 0 on all 8 decode steps. This script fault-injects that instrument
# to prove the zero is a measurement and not a tautology.
#
# READOUT: EQUIVALENCE_EXACT_STEPS, the count of decode steps whose logit error
# is exactly 0. Clean tree = 8.
#
# PASS = every permutation fault arm reports EQUIVALENCE_EXACT_STEPS < 8 AND
# the control arm reports 8 on the same tree. That is the statement "the oracle
# would have caught a lane-major addressing error", which is what B needs.
# ROUND 1 RESULT (modes 5, 6, 1, 0): all four arms reported
# EQUIVALENCE_EXACT_STEPS=8 with byte-identical reports, including the same
# prefill mean 0.011933609. That is ambiguous between two very different
# worlds:
#
#   (a) the oracle reaches lane-major but is insensitive to permutations, or
#   (b) the lane-major kernel never dispatches inside the oracle at all,
#       in which case V2's 8/8 is a tautology and B has NO addressing evidence.
#
# ROUND 2 separates them with a CATASTROPHIC fault. Mode 3 zeroes every fitting
# code, which forces scale -> 0 and produced 32/32 greedy divergences in the
# worker. If mode 3 still reports 8 exact steps here, the kernel is unreachable
# in the oracle (world b). The dispatch log is also enabled so reachability is
# witnessed directly rather than inferred.
set -u
cd "$(dirname "$0")/.."

run_arm() {
    local label="$1" mode="$2"
    echo "=== ${label} (DARKBLOOM_LM_FAULT=${mode}) ==="
    env DARKBLOOM_LM_FAULT="${mode}" DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
        bash research/run_upstream_equivalence.sh 2>&1 \
        | grep -E "EQUIVALENCE_EXACT_STEPS|EQUIVALENCE_EXIT|maximumAbsoluteLogitError|oracle report missing|lane-major|narrow-scales|declined|inactive" \
        | sort | uniq -c | sed 's/^/  /'
    echo
}

run_arm "MODE 3 zero every fitting-arm code (catastrophic; MUST break)" 3
run_arm "MODE 4 zero every escape-arm code (catastrophic; MUST break)" 4
run_arm "CONTROL same tree, no fault (must be 8 exact steps)" 0
