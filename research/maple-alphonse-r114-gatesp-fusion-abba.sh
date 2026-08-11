#!/usr/bin/env bash
# R114-E Stage 3 paired ABBA for the QKV + gate_sp grid-append fusion.
#
# Both arms come from ONE build; the arm selector is an environment flag read
# once per worker process, so the only difference between arms is which
# dispatch shape the scored decode path takes.
#
#   C = DARKBLOOM_DECODE_QKV_GATE_FUSED=0   shipped two-dispatch path
#                                           (bit-identical to BASE_SHA)
#   F = (unset)                             fused single dispatch: the
#                                           heads/8 gate tiles lead the
#                                           lane-major QKV grid
#
# Default order is palindromic so a monotone drift in host state cancels in
# the paired mean.  `--local-iterate` is directional M4 evidence, never a
# ranked claim.
#
# Usage: research/maple-alphonse-r114-gatesp-fusion-abba.sh [ORDER] [OUT_TSV]
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-CFFCCFFC}"
OUT="${2:-/tmp/r114-gatesp-fusion.tsv}"
printf 'idx\tarm\tdecode_s_per_token\tprefill_s_per_token\tpassed\terror\n' > "$OUT"

export MLXFAST_LOCAL_FAN_PROMPT=0

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  log="/tmp/r114_gatesp_fusion_${i}_${arm}.log"
  case "$arm" in
    C) DARKBLOOM_DECODE_QKV_GATE_FUSED=0 ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
    *) ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
  esac
  dec=$(grep -o '"decode_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pre=$(grep -o '"prefill_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pas=$(grep -o '"passed_correctness" : [a-z]*' "$log" | tail -1 | awk '{print $3}')
  err=$(grep -o '"error" : "[^"]*"' "$log" | tail -1 | cut -c11- | tr -d '"')
  printf '%d\t%s\t%s\t%s\t%s\t%s\n' \
    "$i" "$arm" "${dec:-NA}" "${pre:-NA}" "${pas:-NA}" "${err:-}" | tee -a "$OUT"
done

echo "--- $OUT ---"
cat "$OUT"
