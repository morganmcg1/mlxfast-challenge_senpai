#!/usr/bin/env bash
# R103-B optional causal probe: paired A/B of DARKBLOOM_ROUTER_WEIGHT_PREFETCH
# on the NEW (assignment-base) runtime, using ./benchmark.sh --local-iterate.
#
# PF=1 is the shipped NEW default and compiles the `_pf1` router kernel.
# PF=0 restores the OLD router kernel text bit-exactly (proven in rung 1), so
# the two arms differ only in mechanism A while sharing one binary, one
# metallib and one host session. Arms alternate so host thermal drift is
# first-order cancelled; the first leg is discarded as warm-up.
#
# Directional M4 evidence only: the ranked host is M5.
set -u

REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OUT="${OUT:-/tmp/r103b/ab}"
LEGS="${LEGS:-20}"

mkdir -p "$OUT"
cd "$REPO" || exit 1

export MLXFAST_LOCAL_FAN_PROMPT=0

for ((leg = 1; leg <= LEGS; leg++)); do
  if ((leg % 2 == 1)); then pf=1; else pf=0; fi
  tag=$(printf "leg%02d_pf%d" "$leg" "$pf")
  echo "=== $(date -u +%FT%TZ) $tag start ==="
  rm -f score.local-iterate.json
  DARKBLOOM_ROUTER_WEIGHT_PREFETCH="$pf" \
    ./benchmark.sh --local-iterate >"$OUT/$tag.log" 2>&1
  rc=$?
  if [[ -f score.local-iterate.json ]]; then
    cp score.local-iterate.json "$OUT/$tag.json"
    spt=$(python3 -c "import json,sys;print(json.load(open('$OUT/$tag.json'))['metrics']['decode_seconds_per_token'])" 2>/dev/null)
    pspt=$(python3 -c "import json,sys;print(json.load(open('$OUT/$tag.json'))['metrics']['prefill_seconds_per_token'])" 2>/dev/null)
    ok=$(python3 -c "import json,sys;print(json.load(open('$OUT/$tag.json'))['metrics']['passed_correctness'])" 2>/dev/null)
    echo "$tag rc=$rc pf=$pf decode_spt=$spt prefill_spt=$pspt correct=$ok" | tee -a "$OUT/summary.tsv"
  else
    echo "$tag rc=$rc pf=$pf NO_SCORE" | tee -a "$OUT/summary.tsv"
  fi
done

echo "=== $(date -u +%FT%TZ) done ==="
