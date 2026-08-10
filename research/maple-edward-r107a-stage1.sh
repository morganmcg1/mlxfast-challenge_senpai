#!/usr/bin/env bash
# Research-only (PR #629, R107-A) stage 1: rotated-palindrome, position-matched
# full-decode timing of the routed gate/up packing curve S in {2,4,8,16} against
# the shipped default, all five arms driven from one worker binary by
# DARKBLOOM_ROUTED_GATEUP_SG so no build-to-build variation enters any contrast.
#
# `sg2` is the rule-79 identical-code cell: same math and same rendered Metal
# source as `base`, only a different pipeline name and a separate JIT library.
#
# 22 repetitions x 10 slots, 2 discarded, 20 measured -> 40 slots per arm and
# four complete rotation cycles for the analyzer's cycle-blocked contrast.
set -uo pipefail

export SNAP="${SNAP:-/tmp/maple-r107a-snap}"
export OUT="${OUT:-/tmp/maple-r107a/stage1}"
export DESIGN=rotate
export REPS="${REPS:-22}"
export WARMUP_REPS="${WARMUP_REPS:-2}"
export STEPS="${STEPS:-250}"
export ARMS="base:new \
sg2:new:DARKBLOOM_ROUTED_GATEUP_SG=2 \
sg4:new:DARKBLOOM_ROUTED_GATEUP_SG=4 \
sg8:new:DARKBLOOM_ROUTED_GATEUP_SG=8 \
sg16:new:DARKBLOOM_ROUTED_GATEUP_SG=16"
export ASSERT_DIFFER=""
export ASSERT_SAME=""

bash research/maple-frieren-r103a-abba.sh
rc=$?
python3 research/maple-frieren-r103a-analyze-multi.py "${OUT}" \
  "${WARMUP_REPS}" | tee "${OUT}/analysis.txt"
exit ${rc}
