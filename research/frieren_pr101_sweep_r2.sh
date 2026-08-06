#!/bin/bash
# Research-only: PR #101 sweep, replicate 2 in reverse order.
# Round 1 walks the geometries forward, round 2 walks them backward, so any
# monotone host drift over the ~10 min sweep enters the two replicates with
# opposite sign and cancels in the per-point mean.
set -u
cd "$(dirname "$0")/.."
OUT=research/pr101-sweep-r2
mkdir -p "$OUT"
STEPS="${STEPS:-160}"

run_point() {
  local tag="$1"; shift
  local log="$OUT/$tag.txt"
  echo "=== $tag ($*) ==="
  env "$@" python3 research/decode_probe.py --steps "$STEPS" \
      --stderr "$OUT/$tag.worker.err" >"$log" 2>&1
  echo "exit=$?"
  grep -E 'divergence|^decode steps' "$log"
}

run_point "oproj_hoist_off" DARKBLOOM_OPROJ_LM_HOIST=0
run_point "oproj_hoist_on" DARKBLOOM_OPROJ_LM_HOIST=1

for R in 1 2 4; do
  for NS in 1 2 4; do
    run_point "gatesp_r${R}n${NS}" DARKBLOOM_GATESP_R="$R" DARKBLOOM_GATESP_NS="$NS"
  done
done
