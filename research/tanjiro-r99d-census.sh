#!/bin/bash
# r99-D decode-pool census on the rebased frontier (research-only).
# Usage: tanjiro-r99d-census.sh <split 0|1> <reps> <tag>
set -u
cd "$(dirname "$0")/.."
SPLIT="$1"; REPS="$2"; TAG="$3"
mkdir -p research/r99d-logs
for r in $(seq 1 "$REPS"); do
  echo "=== census $TAG rep $r (SPLIT=$SPLIT) $(date -u +%FT%TZ) ==="
  env DARKBLOOM_GPU_PROFILE=1 "DARKBLOOM_GPU_PROFILE_SPLIT=$SPLIT" \
      python3 research/decode_probe.py --steps 80 --profile --profile-top 250 \
      --stderr "research/r99d-logs/${TAG}.${r}.worker.err" \
      > "research/r99d-logs/${TAG}.${r}.log" 2>&1
  echo "rep $r rc=$? -> research/r99d-logs/${TAG}.${r}.log"
  tail -3 "research/r99d-logs/${TAG}.${r}.log"
done
