#!/bin/bash
# Research-only (PR #456): run the four pre-registered GPU-busy contrasts of
# the split-neutrality ABBA campaign in one pass.
#
# `cbs_per_step` is NOT inherited from PR #457. It is re-derived from this
# session's own GPUPROF stream and passed in explicitly, so a change in
# dispatch structure would surface as an argument mismatch rather than a
# silently mis-windowed comparison.
set -uo pipefail

OUT="${OUT:-/tmp/maple-r85b-split}"
CBS="${CBS:-406}"
STEPS="${STEPS:-200}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ERRS=("$OUT"/[0-9]*.err)

run() {
  local tag="$1" a="$2" b="$3" off="$4"
  echo
  echo "############################################################"
  echo "# $tag :: --arms $a $b --offset $off"
  echo "############################################################"
  python3 "$HERE/maple_r85_arm_stats.py" \
    --steps "$STEPS" --cbs-per-step "$CBS" \
    --arms "$a" "$b" --offset "$off" \
    --scale-to-n 16 --min-us-step 5.0 \
    --json-out "$OUT/armstats-$tag.json" \
    "${ERRS[@]}"
  echo "# exit=$?"
}

echo "campaign: $OUT"
echo "cbs-per-step: $CBS (re-derived this session)   steps: $STEPS"
echo "runs: ${#ERRS[@]}"

run effect  base  cand  0
run lottery cand  cand2 1
run null-c2 cand2 cand2 0
run null-b  base  base  1

echo
echo "########## contrasts done ##########"
