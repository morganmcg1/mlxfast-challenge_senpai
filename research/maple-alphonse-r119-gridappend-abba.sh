#!/usr/bin/env bash
# R119-A paired ABBA for the routed-grid append family (instances 2 and 3).
#
# One build, one env selector read once per worker process, so the only
# difference between arms is which dispatch shape the scored decode path takes.
#
#   C = DARKBLOOM_GRID_APPEND=0    shipped separate dispatches (== BASE_SHA)
#   N = DARKBLOOM_GRID_APPEND=0    byte-identical negative control
#   F = DARKBLOOM_GRID_APPEND=2    shared-expert SwiGLU appended (instance 2)
#   H = DARKBLOOM_GRID_APPEND=3    router top-8 appended (instance 3)
#   G = DARKBLOOM_GRID_APPEND=23   both appended
#   E = DARKBLOOM_GRID_APPEND=0 + DARKBLOOM_DECODE_QKV_GATE_FUSED=0
#       R114-E reproduction probe on the merged head (gate->QKV fusion off)
#
# Each run is one isolated worker process driven by research/decode_probe.py:
# a 512-token seed forward followed by --steps single-token decode steps, with
# the per-step wall time dumped one sample per line. The first
# R119_WARMUP_STEPS samples are discarded by the stats script.
#
# Usage: research/maple-alphonse-r119-gridappend-abba.sh [ORDER] [OUTDIR] [STEPS]
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-CNHFGE}"
OUTDIR="${2:-/tmp/r119-gridappend}"
STEPS="${3:-640}"
mkdir -p "$OUTDIR"

arm_mode() {
  case "$1" in
    C|N|E) echo 0 ;;
    F) echo 2 ;;
    H) echo 3 ;;
    G) echo 23 ;;
    *) echo "unknown arm $1" >&2; exit 2 ;;
  esac
}

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  tag=$(printf '%s_%02d_%s' "$(basename "$OUTDIR")" "$i" "$arm")
  csv="$OUTDIR/${tag}.steps.csv"
  log="$OUTDIR/${tag}.log"
  mode=$(arm_mode "$arm")
  qkv=1
  [[ "$arm" == "E" ]] && qkv=0
  DARKBLOOM_GRID_APPEND="$mode" DARKBLOOM_DECODE_QKV_GATE_FUSED="$qkv" \
    python3 research/decode_probe.py \
    --steps "$STEPS" --dump-steps "$csv" \
    --stderr "$OUTDIR/${tag}.worker.err" > "$log" 2>&1
  rc=$?
  div=$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "$log" | awk '{print $4}')
  med=$(grep -o 'median=[0-9.]*' "$log" | head -1 | cut -d= -f2)
  printf '%d\t%s\tmode=%s\trc=%d\tdivergences=%s\tmedian_ms=%s\n' \
    "$i" "$arm" "$mode" "$rc" "${div:-NA}" "${med:-NA}"
done
