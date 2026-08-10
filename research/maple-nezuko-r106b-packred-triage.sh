#!/usr/bin/env bash
# R106-B Stage B triage for Amendment 1 (H-PACKRED candidate + D-SIMDSUM probe).
#
# NOT EVIDENCE.  Rule 86 forbids treating `--local-iterate` numbers as evidence;
# the sole purpose here is to establish the *sign* of each arm before spending
# the preregistered `--local-submit` budget.
#
# Arms:
#   C = no gate                                      shipped 2-head sliding kernel
#   K = DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1       packed float2/float4 butterfly
#   P = DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1      probe; row-loop reduction
#                                                    deleted => WRONG OUTPUT on
#                                                    purpose, `passed` is
#                                                    expected to be false.
#
# Usage: research/maple-nezuko-r106b-packred-triage.sh [ORDER]
#   ORDER default "KCKCPC"
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-KCKCPC}"
# Written outside the worktree so a run never dirties the assignment checkout.
OUT="${OUT:-/tmp/r106b-packred-triage.tsv}"
printf 'idx\tarm\tdecode_s_per_token\tprefill_s_per_token\tpassed\n' > "$OUT"

export MLXFAST_LOCAL_FAN_PROMPT=0

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  log="/tmp/r106b_packred_triage_${i}_${arm}.log"
  case "$arm" in
    K) DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1 ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
    P) DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1 ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
    *) ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
  esac
  dec=$(grep -o '"decode_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pre=$(grep -o '"prefill_seconds_per_token" : [0-9.e-]*' "$log" | tail -1 | awk '{print $3}')
  pas=$(grep -o '"passed_correctness" : [a-z]*' "$log" | tail -1 | awk '{print $3}')
  printf '%d\t%s\t%s\t%s\t%s\n' "$i" "$arm" "${dec:-NA}" "${pre:-NA}" "${pas:-NA}" | tee -a "$OUT"
done

echo "--- $OUT ---"
cat "$OUT"
