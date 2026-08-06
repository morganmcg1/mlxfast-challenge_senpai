#!/bin/bash
# Research-only: PR #101 replicate 2.
#
# Two blocks, both designed against host drift:
#
#   1. Arm B (o_proj lane-major scale-base hoist) as a 4-point ABBA at a higher
#      step count. OFF/ON/ON/OFF cancels any linear drift exactly in the paired
#      contrast, which round 1 (a single OFF then ON pair) could not do. Arm B
#      is the only arm that moved in round 1, so it gets the longer runs.
#
#   2. Arm A (gate_sp geometry) walked backward. Round 1 walked the geometries
#      forward, so monotone drift over the ~8 min block enters the two
#      replicates with opposite sign and cancels in the per-point mean.
set -u
cd "$(dirname "$0")/.."
OUT=research/pr101-sweep-r2
mkdir -p "$OUT"
STEPS="${STEPS:-160}"
ARMB_STEPS="${ARMB_STEPS:-400}"

run_point() {
  local tag="$1"; local steps="$2"; shift 2
  local log="$OUT/$tag.txt"
  echo "=== $tag steps=$steps ($*) ==="
  env "$@" python3 research/decode_probe.py --steps "$steps" \
      --dump-steps "$OUT/$tag.steps.txt" \
      --stderr "$OUT/$tag.worker.err" >"$log" 2>&1
  echo "exit=$?"
  grep -E 'divergence|^decode steps' "$log"
}

run_point "armb_off_a" "$ARMB_STEPS" DARKBLOOM_OPROJ_LM_HOIST=0
run_point "armb_on_b"  "$ARMB_STEPS" DARKBLOOM_OPROJ_LM_HOIST=1
run_point "armb_on_c"  "$ARMB_STEPS" DARKBLOOM_OPROJ_LM_HOIST=1
run_point "armb_off_d" "$ARMB_STEPS" DARKBLOOM_OPROJ_LM_HOIST=0

for R in 1 2 4; do
  for NS in 1 2 4; do
    run_point "gatesp_r${R}n${NS}" "$STEPS" \
      DARKBLOOM_GATESP_R="$R" DARKBLOOM_GATESP_NS="$NS"
  done
done
