#!/usr/bin/env bash
# Stage 0 (R106-F'): time the pinned ranked-baseline tree (15852ee5) and the
# candidate tree back to back in one host session and check whether the M4
# ratios reproduce the harness-published 2.8312x decode / 1.9834x prefill.
#
# Arm order is counterbalanced ABBA so a linear thermal/DVFS drift over the
# session cancels in the paired ratio instead of loading onto one arm.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
BASE_WORKER="${BASE_WORKER:-/tmp/r106f/base/mlxfast-runtime-worker}"
CAND_WORKER="${CAND_WORKER:-$REPO/.build-worker/release/mlxfast-runtime-worker}"
OUT="${OUT:-research/pr270-logs-r106f}"
REPS="${REPS:-6}"
DECODE="${DECODE:-40}"
SETTLE="${SETTLE:-20}"
ORDER="${ORDER:-cand base base cand}"
mkdir -p "$OUT"
unset DARKBLOOM_GPU_PROFILE DARKBLOOM_GPU_PROFILE_SPLIT
# Both trees read the same env knob (RuntimeStartupMemoryPolicy.swift), so
# pinning it keeps the allocator profile symmetric across arms and identical to
# the Stage 1 census session.
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full

for w in "$BASE_WORKER" "$CAND_WORKER"; do
  [ -x "$w" ] || { echo "FATAL: worker missing: $w" >&2; exit 1; }
  echo "$(shasum -a 256 "$w" | cut -d' ' -f1)  $(stat -f '%z' "$w") bytes  $w"
done

i=0
for arm in $ORDER; do
  i=$((i + 1))
  case "$arm" in
    cand) W="$CAND_WORKER" ;;
    base) W="$BASE_WORKER" ;;
    *) echo "FATAL: unknown arm $arm" >&2; exit 1 ;;
  esac
  echo "### settle ${SETTLE}s"
  sleep "$SETTLE"
  echo "### slot $i arm=$arm worker=$W"
  PREFILL_PROBE_WORKER="$W" python3 research/prefill_probe.py \
    --reps "$REPS" --decode-steps "$DECODE" \
    --weights "$REPO/weights" \
    --stderr "$OUT/calib.$i.$arm.worker.err" \
    2>&1 | tee "$OUT/calib.$i.$arm.log"
done
echo "### done"
