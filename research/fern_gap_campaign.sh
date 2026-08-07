#!/usr/bin/env bash
# Research-only decode boundary-gap campaign (PR #241, not submitted).
# One worker process per site, strictly sequential: only one model-holding
# process may run on the host at a time.
set -u
cd "$(dirname "$0")/.."
OUT="${1:-/tmp/fern241}"
SCHED="${2:-0,1,2,4,8,8,4,2,1,0}"
BLOCKS="${3:-3}"
STEPS="${4:-216}"
mkdir -p "$OUT"
for SITE in T0b_qkv T2c_routed_qmv T2d_down_residual T2a_shared_qmv T1c_lmhead T0a_router_top8; do
  echo "=== ${SITE} ==="
  python3 research/fern_gap_probe.py --site "$SITE" \
    --schedule "$SCHED" --blocks "$BLOCKS" --steps-per-segment "$STEPS" \
    --drop 24 --out "${OUT}/gap_${SITE}.tsv"
  echo "=== ${SITE} exit=$? ==="
done
