#!/usr/bin/env bash
# Research-only additivity control for PR #241 (not submitted).
#
# The census (section 2) prices ONE injected boundary at a time. The write-up's
# operational recommendation -- bundle 2-3 dispatch removals into one ranked
# receipt so the effect clears the noise floor -- assumes those prices ADD. If
# the per-boundary cost is instead shared or saturating (e.g. a second injected
# barrier partly reuses the first's tracking-set flush), a bundle is worth less
# than the sum of its parts and the recommendation is wrong.
#
# Arms, all three driven back-to-back in ONE session so they are matched:
#   solo_T0b   T0b_qkv           40 calls/step, PR #218 elasticity E = +0.741
#   solo_T0a   T0a_router_top8   39 calls/step, E = -0.045 (fully shadowed)
#   both       both armed together
#
# Additive prediction for `both` is slope(solo_T0b) + slope(solo_T0a). Running
# the solo arms in the same session as the joint arm also re-tests the
# flat-across-elasticity result without any cross-session confound.
set -u
cd "$(dirname "$0")/.."
OUT="${1:-/tmp/fern241}"
SCHED="${2:-0,1,2,4,8,8,4,2,1,0}"
BLOCKS="${3:-3}"
STEPS="${4:-216}"
mkdir -p "$OUT"

run() { # tag site-list
  echo "=== $1 site=$2 ==="
  python3 research/fern_gap_probe.py --site "$2" --schedule "$SCHED" \
    --blocks "$BLOCKS" --steps-per-segment "$STEPS" --drop 24 \
    --out "${OUT}/$1.tsv"
  echo "=== $1 exit=$? ==="
}

run add_solo_T0b T0b_qkv
run add_solo_T0a T0a_router_top8
run add_both "T0b_qkv,T0a_router_top8"
