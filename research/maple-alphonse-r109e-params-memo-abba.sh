#!/usr/bin/env bash
# R109-E second deliverable: A/B for the full-attention `params` single-entry memo.
#
# Unlike the QK ceiling probe, both arms run the SAME BINARY -- the memo is
# gated at runtime by DARKBLOOM_FULL_PARAMS_MEMO, so no rebuild separates the
# arms and the only difference is whether nine of ten per-step MLXArray
# constructions happen.  Both arms are bit-exact and must report
# passed_correctness=true; a false in either arm invalidates the pair.
#
# Arms:
#   M = memo on  (default; DARKBLOOM_FULL_PARAMS_MEMO unset)
#   O = memo off (DARKBLOOM_FULL_PARAMS_MEMO=0, i.e. shipped per-call behaviour)
#
# Usage: research/maple-alphonse-r109e-params-memo-abba.sh [ORDER] [OUT_TSV]
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-OMMOOMMO}"
OUT="${2:-/tmp/r109e-params-memo.tsv}"
printf 'idx\tarm\tdecode_s_per_token\tprefill_s_per_token\tpassed\terror\n' > "$OUT"

export MLXFAST_LOCAL_FAN_PROMPT=0

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  log="/tmp/r109e_params_memo_${i}_${arm}.log"
  case "$arm" in
    O) DARKBLOOM_FULL_PARAMS_MEMO=0 ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
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
