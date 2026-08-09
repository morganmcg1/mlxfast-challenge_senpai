#!/bin/bash
# Local M4 Pro reachability + slope probe for the source-constant dispatch
# ladder. Uses the env-var form of the same knobs so no rebuild is needed per
# rung; the source-constant build is verified separately to land on the same
# rung. Directional evidence only - the ranked M5 decides.
#
# usage: local_ladder_probe.sh [steps]
set -u

STEPS="${1:-200}"
OUT="/tmp/r93/local-ladder"
mkdir -p "$OUT"

run() {
  local k="$1" tag="$2"
  DARKBLOOM_INJECT_DECODE_EMPTY="$k" DARKBLOOM_INJECT_EMPTY_TG=8 \
    python3 research/decode_probe.py --steps "$STEPS" \
      --stderr "${OUT}/worker-${tag}.err" \
      --dump-tokens "${OUT}/tokens-${tag}.txt" \
      --dump-steps "${OUT}/steps-${tag}.txt" \
      > "${OUT}/probe-${tag}.log" 2>&1
  echo "=== K=${k} tag=${tag} rc=$? $(date -u +%H:%M:%SZ)"
  grep -E "teacher-forced|^decode steps=" "${OUT}/probe-${tag}.log" || tail -3 "${OUT}/probe-${tag}.log"
  shasum -a 256 "${OUT}/tokens-${tag}.txt" | awk '{print "tokens_sha256="$1}'
}

echo "start=$(date -u +%Y-%m-%dT%H:%M:%SZ) steps=${STEPS}"
for pass in a b; do
  for k in 0 40 120 240; do
    run "$k" "${pass}-K${k}"
  done
done
echo "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
