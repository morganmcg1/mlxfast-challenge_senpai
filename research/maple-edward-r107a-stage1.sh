#!/usr/bin/env bash
# Research-only (PR #629, R107-A) stage 1: rotated-palindrome, position-matched
# full-decode timing of the routed gate/up packing curve S in {2,4,8,16} against
# the shipped default, all six arms driven from one worker binary by
# DARKBLOOM_ROUTED_GATEUP_SG so no build-to-build variation enters any contrast.
#
# Two nulls bracket every dose, and they answer different questions:
#
#   base -> null1  rule-79 identical-execution null. The selector accepts only
#                  {2,4,8,16,32}, so SG=1 parses to 0, the _sgN pipeline is
#                  never built and the untouched shipped path runs. Same binary,
#                  same kernel, same dispatch: this cell is pure session noise.
#   base -> sg2    mechanism null. Identical geometry, arithmetic and rendered
#                  Metal body, but a distinct pipeline name, a separate JIT
#                  library and one extra branch, so it prices the machinery
#                  itself apart from any geometry effect.
#
# 24 repetitions x 12 slots. The rotation cycle is 6 repetitions, so the
# discarded warmup is one whole cycle and the 18 measured repetitions are three
# whole cycles: 36 measured slots per arm with every arm at every position.
set -uo pipefail

export SNAP="${SNAP:-/tmp/maple-r107a-snap}"
export OUT="${OUT:-/tmp/maple-r107a/stage1}"
export DESIGN=rotate
export REPS="${REPS:-24}"
export WARMUP_REPS="${WARMUP_REPS:-6}"
export STEPS="${STEPS:-250}"
export ARMS="base:new \
null1:new:DARKBLOOM_ROUTED_GATEUP_SG=1 \
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
