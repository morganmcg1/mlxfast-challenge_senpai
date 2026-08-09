#!/usr/bin/env bash
# R97-B: same-binary alternating A/B for DARKBLOOM_FUSED_QKV on the local host.
#
# A = off (DARKBLOOM_FUSED_QKV=0) reproduces base behaviour exactly: with no
# bank present, the decode guard this arm relaxed is equivalent to the original.
# B = on (default in this tree).
#
# Usage: research/tanjiro-r97-ab.sh [repeats]
# Writes research/r97-logs/ab.<i>.<tag>.{json,log}
set -uo pipefail
cd "$(dirname "$0")/.."
REPEATS="${1:-3}"
OUT=research/r97-logs
mkdir -p "${OUT}"

for i in $(seq 1 "${REPEATS}"); do
  for TAG in off on; do
    if [ "${TAG}" = "on" ]; then
      export DARKBLOOM_FUSED_QKV=1
    else
      export DARKBLOOM_FUSED_QKV=0
    fi
    log="${OUT}/ab.${i}.${TAG}.log"
    echo "r97-ab: rep=${i} tag=${TAG} DARKBLOOM_FUSED_QKV=${DARKBLOOM_FUSED_QKV}" | tee "${log}"
    ./benchmark.sh --local-iterate 2>&1 | tee -a "${log}"
    status="${PIPESTATUS[0]}"
    if [ -f score.local-iterate.json ]; then
      cp score.local-iterate.json "${OUT}/ab.${i}.${TAG}.json"
    fi
    echo "r97-ab: rep=${i} tag=${TAG} exit=${status}"
    if [ "${status}" -ne 0 ]; then exit "${status}"; fi
  done
done
