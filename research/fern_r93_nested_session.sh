#!/usr/bin/env bash
# R93-B nested-design session driver (research only, not part of the submission).
#
# Runs P worker processes back to back, one at a time, each holding the model
# for R `decode_begin` runs of S steps. Every process waits behind the same
# GPU-temperature gate the campaign uses, so no process starts hotter than its
# predecessors did.
#
#   OUT=/tmp/r93/stage1 P=8 R=6 S=200 SCHEDULE=const:0 \
#     bash research/fern_r93_nested_session.sh
#
# SCHEDULES may be a ';'-separated list; process i uses entry (i mod n), which
# is how a counterbalanced arm order is expressed at the process level.
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/bin:$PATH"

OUT="${OUT:?set OUT}"
P="${P:-8}"
R="${R:-6}"
S="${S:-200}"
WARMUP_RUNS="${WARMUP_RUNS:-1}"
SCHEDULES="${SCHEDULES:-${SCHEDULE:-const:0}}"
GATE_C="${GATE_C:-40}"
GATE_MAX_WAIT="${GATE_MAX_WAIT:-600}"
GLUE_MAP="${GLUE_MAP:-$OUT/glue.bin}"
WORKERS="${WORKERS:-.build-worker/release/mlxfast-runtime-worker}"

mkdir -p "$OUT"
IFS=';' read -r -a SCHED_ARR <<< "$SCHEDULES"
NSCHED=${#SCHED_ARR[@]}
IFS=';' read -r -a WORKER_ARR <<< "$WORKERS"
NWORKER=${#WORKER_ARR[@]}

gpu_temp() {
  macmon pipe -s 1 2>/dev/null | head -1 \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["temp"]["gpu_temp_avg"])' \
    2>/dev/null || echo "nan"
}

cool_down() {
  local waited=0
  while :; do
    local t; t=$(gpu_temp)
    local ok; ok=$(python3 -c "import sys;t=float('$t' if '$t'!='nan' else 'nan');print(1 if not (t==t) or t<=$GATE_C else 0)")
    if [ "$ok" = "1" ]; then
      echo "gate: gpu ${t}C <= ${GATE_C}C after ${waited}s"
      return 0
    fi
    if [ "$waited" -ge "$GATE_MAX_WAIT" ]; then
      echo "gate: WARNING still ${t}C after ${waited}s, proceeding"
      return 0
    fi
    echo "waiting for GPU to cool down (${t}C > ${GATE_C}C)"
    sleep 15
    waited=$((waited + 15))
  done
}

echo "session P=$P R=$R S=$S schedules=[$SCHEDULES] out=$OUT"
for ((p = 0; p < P; p++)); do
  sched="${SCHED_ARR[$((p % NSCHED))]}"
  worker="${WORKER_ARR[$((p % NWORKER))]}"
  cool_down
  echo "=== process $p schedule=$sched worker=$worker $(date -u +%H:%M:%S) ==="
  DECODE_PROBE_WORKER="$worker" python3 research/fern_r93_nested_probe.py \
    --runs "$R" --steps "$S" --warmup-runs "$WARMUP_RUNS" \
    --process-index "$p" \
    --label "$sched|$(basename "$(dirname "$worker")")/$(basename "$worker")" \
    --schedule "$sched" \
    --glue-map "$GLUE_MAP" \
    --stderr "$OUT/p$(printf '%02d' "$p").err" \
    --out "$OUT/p$(printf '%02d' "$p").json" || exit 1
done
echo "session done -> $OUT"
