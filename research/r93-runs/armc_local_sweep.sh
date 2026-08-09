#!/usr/bin/env bash
# Arm C local M4 Pro anchor: rebuild the scored worker at each probe level and
# time decode. Establishes (a) that the source-constant probe is reachable on
# the decode path, (b) that it is bit-exact, and (c) the M4 free-ALU slope at
# the super-knee level, which is the denominator of the M4 -> M5 ratio.
#
# Directional only - the ranked M5 decides.
set -u
cd "$(dirname "$0")/../.."

OUT=/tmp/r93/armc
mkdir -p "$OUT"
STEPS="${1:-200}"
shift || true
SPECS=("$@")
if [ "${#SPECS[@]}" -eq 0 ]; then SPECS=("" routed:fma:0 routed:fma:24); fi

echo "start=$(date -u +%Y-%m-%dT%H:%M:%SZ) steps=${STEPS} specs=${SPECS[*]:-none}"
idx=0
for spec in "${SPECS[@]}"; do
  idx=$((idx + 1))
  tag="${spec//:/-}"
  tag="$(printf '%02d-%s' "$idx" "${tag:-off}")"
  bash research/r93-runs/set_probe.sh "$spec" > "${OUT}/build-${tag}.log" 2>&1
  rc=$?
  echo "--- spec='${spec}' build_rc=${rc} $(date -u +%H:%M:%SZ)"
  if [ "$rc" -ne 0 ]; then tail -20 "${OUT}/build-${tag}.log"; continue; fi
  tail -1 "${OUT}/build-${tag}.log"
  python3 research/decode_probe.py --steps "$STEPS" --free-run \
    --free-run-bootstrap 1234 \
    --stderr "${OUT}/worker-${tag}.err" \
    --dump-tokens "${OUT}/tokens-${tag}.txt" \
    --dump-steps "${OUT}/steps-${tag}.txt" \
    --profile --profile-top 12 \
    > "${OUT}/probe-${tag}.log" 2>&1
  echo "probe_rc=$?"
  grep -E "teacher-forced|free-run|^decode steps=|us/token|ms/step" "${OUT}/probe-${tag}.log" | head -8
  grep -iE "routed_nvfp4_swiglu" "${OUT}/probe-${tag}.log" | head -3
  shasum -a 256 "${OUT}/tokens-${tag}.txt" | awk '{print "tokens_sha256="$1}'
done
# leave the tree in the off state
bash research/r93-runs/set_probe.sh "" > "${OUT}/build-restore.log" 2>&1
echo "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
