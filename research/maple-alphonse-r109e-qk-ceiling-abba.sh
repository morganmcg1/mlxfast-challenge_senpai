#!/usr/bin/env bash
# R109-E Stage 0 ceiling probe for the full-attention QK cross-lane reduction.
#
# NOT A CANDIDATE.  Arm P is numerically wrong by construction; both probe arms
# exist only to bound how much decode time the six QK `simd_sum` allreduces in
# `laguna_full_fused_attn_grow_v1` can possibly be worth.  `--local-iterate` is
# directional M4 evidence, never a ranked claim.
#
# Arms:
#   C = no gate                             shipped full-attention kernel.
#   P = DARKBLOOM_FULL_ATTN_QK_PROBE=bcast  the six QK simd_sum allreduces
#                                           replaced by simd_broadcast_first,
#                                           which keeps the score (and the
#                                           LAGUNA_RESCALE branch) lane-uniform
#                                           so the delta isolates the butterfly
#                                           ladder rather than adding
#                                           divergence.  Removes ~10 slots per
#                                           site.  `passed_correctness` is
#                                           expected to be false.
#   D = DARKBLOOM_FULL_ATTN_QK_PROBE=dose   simd_sum kept, then S is scaled by
#                                           2^-5 and re-doubled through a
#                                           five-stage butterfly.  Bit-exact,
#                                           so `passed_correctness` must stay
#                                           true, while adding ~11 slots per
#                                           site.  P and D therefore bracket
#                                           the ladder from both sides and
#                                           expose a non-linear instrument.
#
# Usage: research/maple-alphonse-r109e-qk-ceiling-abba.sh [ORDER] [OUT_TSV]
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-CDPPDC}"
OUT="${2:-/tmp/r109e-qk-ceiling.tsv}"
printf 'idx\tarm\tdecode_s_per_token\tprefill_s_per_token\tpassed\terror\n' > "$OUT"

export MLXFAST_LOCAL_FAN_PROMPT=0

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  log="/tmp/r109e_qk_ceiling_${i}_${arm}.log"
  case "$arm" in
    P) DARKBLOOM_FULL_ATTN_QK_PROBE=bcast ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
    D) DARKBLOOM_FULL_ATTN_QK_PROBE=dose  ./benchmark.sh --local-iterate > "$log" 2>&1 ;;
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
