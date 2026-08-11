#!/usr/bin/env bash
# fern r109-f: interleaved paired A/B over ./benchmark.sh --local-submit.
#
# Draws alternate A,B,A,B,... so that any monotone thermal or background drift
# over the run is shared equally by both arms instead of loading onto whichever
# arm ran second. Each arm is selected purely by environment, so the Swift
# binary is built once and both arms execute the same executable; note that the
# official timed path strips workflow env (sudo env_reset + env -i), so env is
# an A/B instrument only and never a shipping mechanism.
#
# Usage: research/fern_r109f_paired_ab.sh <pairs> <labelA> <envA> <labelB> <envB>
#   envA/envB are space-separated KEY=VALUE assignments, or "-" for none.
#
# Example:
#   research/fern_r109f_paired_ab.sh 3 tg64 DARKBLOOM_SHARED_QMV_TG256=0 \
#                                      tg256 DARKBLOOM_SHARED_QMV_TG256=1
#
# Per draw i of arm L archives:
#   research/fern-r109f-submit-ladder/<L>-<i>.log        full stdout/stderr
#   research/fern-r109f-submit-ladder/<L>-<i>.json       score.json
#   research/fern-r109f-submit-ladder/<L>-<i>.integrity  benchmark-integrity.json
# The authoritative record is the log: parse it with fern_r109f_parse_ladder.py.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

pairs="${1:?pairs}"
labelA="${2:?labelA}"
envA="${3:?envA}"
labelB="${4:?labelB}"
envB="${5:?envB}"
out="research/fern-r109f-submit-ladder"
mkdir -p "${out}"

run_draw() {
  local label="$1" envspec="$2" i="$3"
  local started t0 t1 rc wall
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  t0="$(date +%s)"
  # shellcheck disable=SC2086
  if [ "${envspec}" = "-" ]; then
    MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-submit \
      > "${out}/${label}-${i}.log" 2>&1
  else
    env MLXFAST_LOCAL_FAN_PROMPT=0 ${envspec} ./benchmark.sh --local-submit \
      > "${out}/${label}-${i}.log" 2>&1
  fi
  rc=$?
  t1="$(date +%s)"
  wall=$(( t1 - t0 ))
  # --local-submit writes score.json / benchmark-integrity.json. Only
  # --local-iterate uses the .local-iterate suffixed names.
  [ -f score.json ] && cp score.json "${out}/${label}-${i}.json"
  [ -f benchmark-integrity.json ] && cp benchmark-integrity.json "${out}/${label}-${i}.integrity"
  echo "DRAW ${label} ${i} started=${started} rc=${rc} wall=${wall}s env=[${envspec}]"
}

echo "paired A/B: ${pairs} pairs, A=${labelA} [${envA}], B=${labelB} [${envB}]"
echo "git HEAD $(git rev-parse HEAD)"
for i in $(seq 1 "${pairs}"); do
  run_draw "${labelA}" "${envA}" "${i}"
  run_draw "${labelB}" "${envB}" "${i}"
done
echo "paired A/B complete"
