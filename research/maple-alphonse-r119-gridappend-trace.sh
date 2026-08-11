#!/usr/bin/env bash
# R119-A dispatch-path trace: confirm the grid-append wrapper is actually taken
# (it returns nil and falls back silently on any guard failure).
set -uo pipefail
cd "$(dirname "$0")/.."

OUTDIR="${1:-/tmp/r119-trace}"
mkdir -p "$OUTDIR"

for mode in 0 2 3 23; do
  err="$OUTDIR/trace_${mode}.err"
  DARKBLOOM_TRACE_FUSION=1 DARKBLOOM_GRID_APPEND="$mode" \
    python3 research/decode_probe.py --steps 4 \
    --stderr "$err" > "$OUTDIR/trace_${mode}.log" 2>&1
  echo "=== mode=$mode rc=$? ==="
  grep -o 'laguna[a-z0-9_ +/()-]*' "$err" 2>/dev/null | sort | uniq -c | sort -rn | head -40
  echo "--- fusion trace lines ---"
  sort -u "$err" 2>/dev/null | grep -i -E 'grid append|shared|router|residual|rmsnorm' | head -40
done
