#!/usr/bin/env bash
# R125-B ladder campaign: the ns axis on the decode QKV projection at rps = 1.
#
# Three arms, all in the SAME append state (grid-append disabled), so the only
# thing that moves between arms is threads-per-threadgroup and the threadgroup
# count. Reference arm is N2 = the shipped 64-thread geometry.
#
#   N2  ns=2   64 threads/TG  5120 TGs (h64)  <-- reference
#   N4  ns=4  128 threads/TG  2560 TGs
#   N8  ns=8  256 threads/TG  1280 TGs        <-- primary
#
# BLOCKS defaults to 4 (12 runs, ~40 min). Rows land outside the worktree.
set -u
cd "$(dirname "$0")/.."
export OUT="${OUT:-/tmp/r125b-certify.tsv}"
export KEEP="${KEEP:-0}"
exec research/maple-nezuko-r107j-certify.sh --blocks "${BLOCKS:-4}" \
  N2:DARKBLOOM_DECODE_QKV_GATE_FUSED=0 \
  N4:DARKBLOOM_DECODE_QKV_GATE_FUSED=0,DARKBLOOM_QKV_SIMDGROUPS=4 \
  N8:DARKBLOOM_DECODE_QKV_GATE_FUSED=0,DARKBLOOM_QKV_SIMDGROUPS=8
