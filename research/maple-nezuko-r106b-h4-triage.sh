#!/usr/bin/env bash
# R106-B Stage B triage (NOT evidence -- Rule 86 forbids treating --local-iterate
# numbers as evidence).  Sole purpose: establish the *sign* of the H4
# head-packing variant cheaply before spending the preregistered
# --local-submit budget on it.
#
# Arms, interleaved ABBA:
#   C = DARKBLOOM_FUSED_SLIDING_ATTN_H4 unset  (shipped 2-head sliding kernel)
#   H = DARKBLOOM_FUSED_SLIDING_ATTN_H4=1      (4-head packed sliding kernel)
#
# Usage: research/maple-nezuko-r106b-h4-triage.sh [ORDER]
#   ORDER default "CHHC"
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-CHHC}"
# Written outside the worktree so a run never dirties the assignment checkout.
OUT="${OUT:-/tmp/r106b-h4-triage.tsv}"
printf 'idx\tarm\tdecode_s_per_token\tprefill_s_per_token\tpassed\n' > "$OUT"

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  log="/tmp/r106b_h4_triage_${i}_${arm}.log"
  if [ "$arm" = "H" ]; then
    DARKBLOOM_FUSED_SLIDING_ATTN_H4=1 ./benchmark.sh --local-iterate > "$log" 2>&1
  else
    ./benchmark.sh --local-iterate > "$log" 2>&1
  fi
  dec=$(grep -o '"decode_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pre=$(grep -o '"prefill_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pas=$(grep -o '"passed_correctness" : [a-z]*' "$log" | tail -1 | awk '{print $3}')
  printf '%d\t%s\t%s\t%s\t%s\n' "$i" "$arm" "${dec:-NA}" "${pre:-NA}" "${pas:-NA}" | tee -a "$OUT"
done

echo "--- $OUT ---"
cat "$OUT"
