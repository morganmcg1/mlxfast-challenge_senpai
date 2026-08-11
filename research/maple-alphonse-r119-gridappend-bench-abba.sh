#!/usr/bin/env bash
# R119-A layer-2 paired ABBA on ./benchmark.sh --local-iterate.
#
# Layer 1 (decode_probe) resolves per-step decode microseconds; this layer
# supplies the ranked-shape numbers the assignment gates on: decode and
# prefill seconds/token from the trusted harness plus passed_correctness.
# Prefill is a hard gate here, so both axes are recorded per run.
#
# Arms use the same single build and the same env selector as layer 1:
#   C = DARKBLOOM_GRID_APPEND=0   shipped separate dispatches (== BASE_SHA)
#   F = 2    shared-expert SwiGLU appended
#   H = 3    router top-8 appended
#   G = 23   both appended
#
# Usage: research/maple-alphonse-r119-gridappend-bench-abba.sh [ORDER] [OUT_TSV]
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-CHHCCHHC}"
OUT="${2:-/tmp/r119-gridappend-bench.tsv}"
printf 'idx\tarm\tmode\tdecode_s_per_token\tprefill_s_per_token\tpassed\terror\n' > "$OUT"

export MLXFAST_LOCAL_FAN_PROMPT=0

arm_mode() {
  case "$1" in
    C) echo 0 ;;
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
  mode=$(arm_mode "$arm")
  log="/tmp/r119_bench_${i}_${arm}.log"
  DARKBLOOM_GRID_APPEND="$mode" ./benchmark.sh --local-iterate > "$log" 2>&1
  dec=$(grep -o '"decode_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pre=$(grep -o '"prefill_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pas=$(grep -o '"passed_correctness" : [a-z]*' "$log" | tail -1 | awk '{print $3}')
  err=$(grep -o '"error" : "[^"]*"' "$log" | tail -1 | cut -c11- | tr -d '"')
  printf '%d\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$i" "$arm" "$mode" "${dec:-NA}" "${pre:-NA}" "${pas:-NA}" "${err:-}" | tee -a "$OUT"
done

echo "--- $OUT ---"
cat "$OUT"
