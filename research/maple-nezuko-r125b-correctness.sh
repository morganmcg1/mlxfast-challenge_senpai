#!/usr/bin/env bash
# R125-B correctness gates for the decode-QKV threadgroup-granularity ladder.
#
# Timings from this script are DISCARDED (it runs --local-iterate, sigma ~33.6 %,
# and it disables the thermal cool gate), so it is only ever used for
# max_abs_diff / golden hash / dispatch-trace evidence. Pricing comes from
# research/maple-nezuko-r107j-certify.sh under --local-submit.
set -u
cd "$(dirname "$0")/.."
OUT="${OUT:-/tmp/nezuko-r125b-correct}"
mkdir -p "$OUT"
export MLXFAST_LOCAL_COOL_GATE=0
export MLXFAST_LOCAL_FAN_PROMPT=0

run_arm () {
  local lab="$1"; shift
  rm -f score.json score.local-iterate.json
  env "$@" DARKBLOOM_TRACE_FUSION=1 ./benchmark.sh --local-iterate \
      > "${OUT}/${lab}.log" 2>&1
  local rc=$?
  echo "=== arm=${lab} rc=${rc} gates='$*'"
  if [ -f score.local-iterate.json ]; then
    cp score.local-iterate.json "${OUT}/${lab}.score.json"
  fi
  grep -E "max_abs_diff|golden_sha256|correctness" "${OUT}/${lab}.log" \
    | head -6
  echo "--- qkv dispatch trace lines:"
  grep -E "decode nvfp4 qkv" "${OUT}/${lab}.log" | sort -u | head -10
}

run_arm S
run_arm N2 DARKBLOOM_DECODE_QKV_GATE_FUSED=0
run_arm N4 DARKBLOOM_DECODE_QKV_GATE_FUSED=0 DARKBLOOM_QKV_SIMDGROUPS=4
run_arm N8 DARKBLOOM_DECODE_QKV_GATE_FUSED=0 DARKBLOOM_QKV_SIMDGROUPS=8
run_arm N16 DARKBLOOM_DECODE_QKV_GATE_FUSED=0 DARKBLOOM_QKV_SIMDGROUPS=16

rm -f score.json score.local-iterate.json
echo "=== upstream equivalence, N8, EQUIVALENCE_EXACT_STEPS=8"
env EQUIVALENCE_EXACT_STEPS=8 DARKBLOOM_DECODE_QKV_GATE_FUSED=0 \
    DARKBLOOM_QKV_SIMDGROUPS=8 research/run_upstream_equivalence.sh \
    > "${OUT}/equiv-n8.log" 2>&1
echo "equiv rc=$?"
tail -25 "${OUT}/equiv-n8.log"
echo "=== done"
