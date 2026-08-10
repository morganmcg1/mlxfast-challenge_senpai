#!/usr/bin/env bash
# R106-B Stage B — EVIDENCE campaign for the PACKRED packed-cross-lane-reduction sliding decode
# attention kernel, exactly as preregistered in
# research/maple-nezuko-r106b-stageb-amendment1.md (section 4.4).
#
# Design: one binary, gate-selected, strictly alternating arms in one session.
#   C = DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED unset  (shipped kernel = preregistered revert)
#   K = DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1      (packed float2/float4 butterfly reduction)
# Path: ./benchmark.sh --local-submit (1023 decode steps). --local-iterate is
# never used here (Rule 86).
#
# Usage: research/maple-nezuko-r106b-packred-paired.sh [ORDER]
#   ORDER default "CKCKCK" (3 preregistered pairs, declared dof = 2)
# Env:
#   OUT=<tsv>   row sink (default /tmp/r106b-packred-paired.tsv; kept outside the
#               worktree so a run never dirties the assignment checkout)
#   KEEP=1      keep the per-run score json copies in /tmp
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${1:-CHCHCH}"
OUT="${OUT:-/tmp/r106b-packred-paired.tsv}"
SESSION="$(date -u +%Y%m%dT%H%M%SZ)"

# Unattended automation: never offer the interactive fan boost; the 40 C
# thermal cool gate still waits and still fails closed before each timed phase.
export MLXFAST_LOCAL_FAN_PROMPT=0

if [ ! -s "$OUT" ]; then
  printf 'session\tidx\tarm\tdecode_s_per_token\tprefill_s_per_token\tpassed\terror\n' > "$OUT"
fi

i=0
for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((i+1))
  log="/tmp/r106b_packred_paired_${SESSION}_${i}${arm}.log"
  score="/tmp/r106b_packred_paired_${SESSION}_${i}${arm}.score.json"
  rm -f score.json
  echo "=== paired arm=${arm} idx=${i} start $(date -u +%H:%M:%S)"
  if [ "$arm" = "K" ]; then
    DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1 ./benchmark.sh --local-submit > "$log" 2>&1
  else
    ./benchmark.sh --local-submit > "$log" 2>&1
  fi
  rc=$?
  git checkout -q -- Package.resolved 2>/dev/null || true
  if [ ! -f score.json ]; then
    echo "FATAL: arm=${arm} idx=${i} produced no score.json (rc=${rc}); see ${log}" >&2
    tail -20 "$log" >&2
    exit 1
  fi
  cp score.json "$score"
  dec=$(jq -r '.metrics.decode_seconds_per_token // "NA"' "$score")
  pre=$(jq -r '.metrics.prefill_seconds_per_token // "NA"' "$score")
  pas=$(jq -r '.metrics.passed_correctness // "NA"' "$score")
  err=$(jq -r '.metrics.error // ""' "$score")
  printf '%s\t%d\t%s\t%s\t%s\t%s\t%s\n' "$SESSION" "$i" "$arm" "$dec" "$pre" "$pas" "$err" | tee -a "$OUT"
  echo "=== paired arm=${arm} idx=${i} done  $(date -u +%H:%M:%S) rc=${rc}"
  [ "${KEEP:-0}" = 1 ] || rm -f "$score"
done

rm -f score.json
echo "--- $OUT ---"
cat "$OUT"
