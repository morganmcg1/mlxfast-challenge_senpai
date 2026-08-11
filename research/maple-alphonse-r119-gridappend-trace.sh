#!/usr/bin/env bash
# R119-A dispatch-path trace: confirm the grid-append wrapper is actually taken
# (it returns nil and falls back silently on any guard failure).
set -uo pipefail
cd "$(dirname "$0")/.."

OUTDIR="${1:-/tmp/r119-trace}"
mkdir -p "$OUTDIR"

for spec in 0:0 2:0 3:0 23:0 5:0 0:1; do
  mode="${spec%%:*}"
  wide8="${spec##*:}"
  err="$OUTDIR/trace_${mode}_w${wide8}.err"
  DARKBLOOM_TRACE_FUSION=1 DARKBLOOM_GRID_APPEND="$mode" \
    DARKBLOOM_SHARED_QMV_WIDE8="$wide8" \
    python3 research/decode_probe.py --steps 4 \
    --stderr "$err" > "$OUTDIR/trace_${mode}_w${wide8}.log" 2>&1
  echo "=== mode=$mode wide8=$wide8 rc=$? ==="
  grep -o 'laguna[a-z0-9_ +/()-]*' "$err" 2>/dev/null | sort | uniq -c | sort -rn | head -40
  echo "--- fusion trace lines ---"
  sort -u "$err" 2>/dev/null | grep -i -E 'grid append|shared|router|residual|rmsnorm' | head -40
done
