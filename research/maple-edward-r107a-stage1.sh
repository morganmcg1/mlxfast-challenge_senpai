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
# 18 repetitions x 12 slots at ~44.5 s per slot is ~2.7 h, which is what fits
# inside the 3 h supervised-job ceiling. The rotation cycle is 6 repetitions, so
# all 18 are three whole cycles: 36 measured slots per arm with every arm at
# every position. Nothing is discarded up front -- a per-repetition paired
# contrast already removes any repetition-level drift, and the analyzer is run a
# second time discarding one whole cycle as a sensitivity check.
set -uo pipefail

export SNAP="${SNAP:-/tmp/maple-r107a-snap}"
export OUT="${OUT:-/tmp/maple-r107a/stage1}"
export DESIGN=rotate
export REPS="${REPS:-18}"
export WARMUP_REPS="${WARMUP_REPS:-0}"
export STEPS="${STEPS:-250}"
# SEL_VAR picks the site: DARKBLOOM_ROUTED_GATEUP_SG is the routed gate/up
# kernel (stage 1), DARKBLOOM_QKV_LM_SG the decode QKV lane-major kernel
# (stage A). SG_LIST is the dose ladder; 1 is always the rejected-value null.
SEL_VAR="${SEL_VAR:-DARKBLOOM_ROUTED_GATEUP_SG}"
SG_LIST="${SG_LIST:-2 4 8 16}"
arms="base:new null1:new:${SEL_VAR}=1"
for s in ${SG_LIST}; do arms="${arms} sg${s}:new:${SEL_VAR}=${s}"; done
export ARMS="${arms}"
# DESIGN=rotate advances the arm order by one slot per repetition, so one whole
# rotation cycle is exactly the arm count. The sensitivity pass drops one cycle.
narms=$(printf '%s\n' ${arms} | wc -l | tr -d ' ')
DROP_CYCLE="${DROP_CYCLE:-${narms}}"
# abba expands these with ${VAR:-default}, so an empty string silently restores
# its oldA/oldB defaults and aborts. Every arm here is one binary driven by env,
# so assert that single-binary invariant and keep cmp itself non-vacuous by
# pairing it with two snapshots that genuinely differ.
export ASSERT_SAME="new:new"
export ASSERT_DIFFER="new:geom"

bash research/maple-frieren-r103a-abba.sh
rc=$?
python3 research/maple-frieren-r103a-analyze-multi.py "${OUT}" \
  "${WARMUP_REPS}" | tee "${OUT}/analysis.txt"
OUT_SENS="${OUT}-drop1cycle"
mkdir -p "${OUT_SENS}"
cp "${OUT}"/index.tsv "${OUT}"/*.steps "${OUT}"/*.log "${OUT_SENS}/" 2>/dev/null
python3 research/maple-frieren-r103a-analyze-multi.py "${OUT_SENS}" "${DROP_CYCLE}" \
  | tee "${OUT}/analysis-drop1cycle.txt"
exit ${rc}
