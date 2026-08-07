#!/bin/bash
# PR284 step 0: price a byte of lm-head screen traffic on this host.
#
# Three same-binary arms, interleaved, no rebuild between them:
#   A  default                                 screen reads 1088 B/row = 109.183 MB
#   B  DARKBLOOM_LMHEAD_FUSED_REFINEMENT=0     screen reads 1344 B/row = 134.873 MB
#   C  DARKBLOOM_LM_HEAD_PRUNE=0               full bf16 lm_head GEMV  = 411.042 MB
#
# B-A and C-A give two independent points on the byte -> microsecond line for
# this exact access pattern, and the interleaving gives a drift/noise estimate.

set -u
cd "$(dirname "$0")/.."
OUT=research/artifacts/nezuko-pr284-byte-price.tsv
mkdir -p research/artifacts
printf 'rep\tarm\tdecode_s_per_token\tprefill_s_per_token\tscore\tpassed\n' >"$OUT"

reps="${REPS:-3}"
for rep in $(seq 1 "$reps"); do
  for arm in A B C; do
    case "$arm" in
      A) env_kv="" ;;
      B) env_kv="DARKBLOOM_LMHEAD_FUSED_REFINEMENT=0" ;;
      C) env_kv="DARKBLOOM_LM_HEAD_PRUNE=0" ;;
    esac
    echo "=== rep $rep arm $arm ${env_kv:-(default)} ==="
    if [ -n "$env_kv" ]; then
      env "$env_kv" ./benchmark.sh --local-iterate >/dev/null 2>&1
    else
      ./benchmark.sh --local-iterate >/dev/null 2>&1
    fi
    rc=$?
    if [ "$rc" -ne 0 ]; then
      echo "arm $arm rep $rep FAILED rc=$rc"
      printf '%s\t%s\tFAIL\tFAIL\tFAIL\tFAIL\n' "$rep" "$arm" >>"$OUT"
      continue
    fi
    python3 - "$rep" "$arm" "$OUT" <<'PY'
import json, sys
rep, arm, out = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open("score.local-iterate.json"))
m = d.get("metrics", d)
with open(out, "a") as f:
    f.write("%s\t%s\t%.9f\t%.9f\t%.6f\t%s\n" % (
        rep, arm, m["decode_seconds_per_token"], m["prefill_seconds_per_token"],
        d.get("score", float("nan")), d.get("passed")))
print("rep %s arm %s decode %.9f prefill %.9f" % (
    rep, arm, m["decode_seconds_per_token"], m["prefill_seconds_per_token"]))
PY
  done
done

echo "=== results ==="
cat "$OUT"
