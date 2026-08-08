#!/usr/bin/env bash
# R86-A Step 2 go/no-go: alternating matched-pair local decode timing for
# base vs 97a5090c content of the one file that carries a real behaviour
# difference (LagunaRuntimeModel.swift, the scored forward pass).
#
# Arms alternate within each repeat so thermal/placement drift is shared.
set -uo pipefail
cd "$(dirname "$0")/.."

FILE="Sources/MLXFastModel/LagunaRuntimeModel.swift"
FRONTIER_REF="149212f78ef630da4e00f1123420fc6250e5e9a9"
OUT="research/r86-pair-results"
mkdir -p "$OUT"

export MLXFAST_LOCAL_FAN_PROMPT=0

# ABBA ordering: the arm that runs first alternates per repeat so any
# within-session warm/cool drift cancels instead of loading onto one arm.
for rep in 1 2 3; do
  if [ $((rep % 2)) -eq 1 ]; then order="rev base"; else order="base rev"; fi
  for arm in $order; do
    if [ "$arm" = "base" ]; then
      git checkout HEAD -- "$FILE"
    else
      git checkout "$FRONTIER_REF" -- "$FILE"
    fi
    echo "=== rep ${rep} arm ${arm} start $(date -u +%FT%TZ) sha=$(shasum -a 256 "$FILE" | cut -c1-12) ==="
    MLXFAST_SCORE_PATH=score.json ./benchmark.sh --local-iterate \
      > "${OUT}/${arm}-r${rep}.log" 2>&1
    status=$?
    echo "=== rep ${rep} arm ${arm} exit ${status} $(date -u +%FT%TZ) ==="
    if [ -f score.json ]; then
      cp score.json "${OUT}/${arm}-r${rep}.json"
      python3 -c "import json;d=json.load(open('score.json'));print({k:d.get(k) for k in ('score','decode_speedup','prefill_speedup','decode_seconds_per_token','prefill_seconds_per_token','passed')})" || true
    fi
  done
done

git checkout HEAD -- "$FILE"
git reset -q HEAD -- "$FILE"
echo "=== done $(date -u +%FT%TZ) ==="
