#!/usr/bin/env bash
# PR270 r2 Task 2.4: matched --local-iterate pair for DARKBLOOM_FUSED_QKV.
# Usage: research/tanjiro_f1_iterate.sh off|on
# Writes research/pr270-logs/f1-iterate.<tag>.{json,log}
set -uo pipefail
cd "$(dirname "$0")/.."
TAG="${1-}"
case "${TAG}" in
  off|on) ;;
  *) echo "usage: $0 off|on" >&2; exit 2 ;;
esac
OUT=research/pr270-logs
mkdir -p "${OUT}"

if [ "${TAG}" = "on" ]; then
  export DARKBLOOM_FUSED_QKV=1
else
  unset DARKBLOOM_FUSED_QKV
fi

# The runtime worker environment is a strict allowlist that keeps the
# DARKBLOOM_ prefix, so record the value this arm actually exported.
echo "tanjiro_f1_iterate: tag=${TAG} DARKBLOOM_FUSED_QKV=${DARKBLOOM_FUSED_QKV-<unset>}" \
  | tee "${OUT}/f1-iterate.${TAG}.log"

./benchmark.sh --local-iterate 2>&1 | tee -a "${OUT}/f1-iterate.${TAG}.log"
status="${PIPESTATUS[0]}"
[ -f score.local-iterate.json ] && cp score.local-iterate.json "${OUT}/f1-iterate.${TAG}.json"
echo "exit=${status} tag=${TAG}"
exit "${status}"
