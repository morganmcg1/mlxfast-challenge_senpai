#!/usr/bin/env bash
# Research-only command-buffer-aliasing control for PR #241 (not submitted).
#
# The default campaign injects 39-40 extra dispatches per copy-set, which on
# this M4 Pro ('g' arch) is almost exactly MLX's max_ops_per_buffer=40. A
# per-dispatch cost and a per-command-buffer cost are therefore degenerate in
# that data. Raising the split thresholds breaks the degeneracy: a per-CB cost
# must fall roughly as 1/max_ops, a per-dispatch cost must not move.
set -u
cd "$(dirname "$0")/.."
OUT="${1:-/tmp/fern241}"
SCHED="0,1,2,4,8,8,4,2,1,0"
mkdir -p "$OUT"

run() { # tag site
  echo "=== $1 site=$2 MLX_MAX_OPS_PER_BUFFER=${MLX_MAX_OPS_PER_BUFFER:-default} MLX_MAX_MB_PER_BUFFER=${MLX_MAX_MB_PER_BUFFER:-default} ==="
  python3 research/fern_gap_probe.py --site "$2" --schedule "$SCHED" \
    --blocks 3 --steps-per-segment 216 --drop 24 --out "${OUT}/$1.tsv"
  echo "=== $1 exit=$? ==="
}

MLX_MAX_OPS_PER_BUFFER=4000 run ops4000_T0b_qkv T0b_qkv
MLX_MAX_OPS_PER_BUFFER=4000 MLX_MAX_MB_PER_BUFFER=100000 \
  run opsmb_T0b_qkv T0b_qkv
MLX_MAX_OPS_PER_BUFFER=4000 MLX_MAX_MB_PER_BUFFER=100000 \
  run opsmb_T0a_router_top8 T0a_router_top8
