#!/usr/bin/env bash
# PR270 r2 Task 2.4: matched --local-iterate pair for DARKBLOOM_FUSED_QKV.
# Usage: research/tanjiro_f1_iterate.sh {off|on}
# Writes research/pr270-logs/f1-iterate.<tag>.{json,log}
set -uo pipefail
cd "$(dirname "$0")/.."
TAG="${1:?usage: $0 {off|on}}"
OUT=research/pr270-logs
mkdir -p "${OUT}"

if [ "${TAG}" = "on" ]; then
  export DARKBLOOM_FUSED_QKV=1
else
  unset DARKBLOOM_FUSED_QKV
fi

./benchmark.sh --local-iterate 2>&1 | tee "${OUT}/f1-iterate.${TAG}.log"
status="${PIPESTATUS[0]}"
[ -f score.local-iterate.json ] && cp score.local-iterate.json "${OUT}/f1-iterate.${TAG}.json"
echo "exit=${status} tag=${TAG}"
exit "${status}"
