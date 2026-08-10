#!/usr/bin/env bash
# R107-E Stage 2: in-situ paired timing of the decode oproj row-per-simdgroup
# geometry over the trusted ./benchmark.sh --local-iterate entrypoint.
#
#   SCHEDULE="g0 g1 g1 g0" bash research/maple-alphonse-r107e-insitu.sh
#
# Every arm runs the SAME worker binary; only DARKBLOOM_OPROJ_GEOM differs, so
# the submitted surface is identical across arms by construction. The g0 arm
# leaves the variable unset, and the offline AIR census in
# research/artifacts/maple-alphonse-r107e/geom-air-ledger.json proves the g0
# emission is byte-identical to the pre-refactor base for both head counts, so
# "env unset" is a sound paired baseline rather than a near-baseline.
#
# Rows accumulate in OUT across invocations; the summary re-reads every row.
set -uo pipefail
cd "$(dirname "$0")/.."

SCHEDULE="${SCHEDULE:-g0 g1 g1 g0}"
OUT="${OUT:-research/artifacts/maple-alphonse-r107e/insitu}"
PRECOOL_SECONDS="${PRECOOL_SECONDS:-120}"
SESSION="${SESSION:-$(date -u +%Y%m%dT%H%M%SZ)}"
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-2}"
mkdir -p "${OUT}"

export PATH="${HOME}/.local/bin:${HOME}/bin:${PATH}"
export MLXFAST_MACMON_BIN="${MLXFAST_MACMON_BIN:-${HOME}/bin/macmon}"
export MLXFAST_GPU_TEMP_CMD="${MLXFAST_GPU_TEMP_CMD:-${MLXFAST_MACMON_BIN} pipe -s1 | jq -M -r '.temp.cpu_temp_avg'}"
export MLXFAST_LOCAL_FAN_PROMPT=0

echo "r107e-insitu: session=${SESSION} schedule=${SCHEDULE} precool=${PRECOOL_SECONDS}s out=${OUT}"
echo "r107e-insitu: head=$(git rev-parse HEAD) dirty=$([ -z "$(git status --porcelain)" ] && echo no || echo yes)"

idx=0
consecutive_failures=0
for arm in ${SCHEDULE}; do
  idx=$((idx + 1))
  tag=$(printf '%s.p%02d.%s' "${SESSION}" "${idx}" "${arm}")
  if [[ "${PRECOOL_SECONDS}" -gt 0 ]]; then
    echo "--- idling ${PRECOOL_SECONDS}s to soak-cool the chassis ---"
    sleep "${PRECOOL_SECONDS}"
  fi
  ./benchmark.sh --local-cool-gate-only >>"${OUT}/precool.log" 2>&1 || true
  rm -f score.local-iterate.json
  echo "=== ${tag} starting $(date -u +%H:%M:%SZ) ==="
  start=${SECONDS}
  if [[ "${arm}" == "g0" ]]; then
    ./benchmark.sh --local-iterate >"${OUT}/${tag}.log" 2>&1
  else
    DARKBLOOM_OPROJ_GEOM="${arm}" ./benchmark.sh --local-iterate >"${OUT}/${tag}.log" 2>&1
  fi
  rc=$?
  dur=$((SECONDS - start))
  git checkout -q -- Package.resolved 2>/dev/null || true
  if [[ -f score.local-iterate.json ]]; then
    cp score.local-iterate.json "${OUT}/${tag}.score.json"
    jq -c --arg session "${SESSION}" --arg arm "${arm}" --argjson pos "${idx}" \
      --argjson dur "${dur}" --arg tag "${tag}" \
      '{session:$session, pos:$pos, arm:$arm, tag:$tag, seconds:$dur,
        decode:.metrics.decode_seconds_per_token,
        prefill:.metrics.prefill_seconds_per_token,
        passed:.metrics.passed_correctness, error:.metrics.error}' \
      "${OUT}/${tag}.score.json" > "${OUT}/${tag}.row.json"
    echo "r107e-insitu: $(cat "${OUT}/${tag}.row.json")"
  else
    echo "r107e-insitu: ${tag} rc=${rc} seconds=${dur} NO SCORE FILE"
    tail -20 "${OUT}/${tag}.log"
  fi
  printf '%s rc=%s seconds=%s\n' "${tag}" "${rc}" "${dur}" | tee -a "${OUT}/summary.txt"
  if [[ "${rc}" -eq 0 ]]; then
    consecutive_failures=0
  else
    consecutive_failures=$((consecutive_failures + 1))
    if [[ "${consecutive_failures}" -ge "${MAX_CONSECUTIVE_FAILURES}" ]]; then
      echo "r107e-insitu: aborting after ${consecutive_failures} consecutive failures" \
        | tee -a "${OUT}/summary.txt"
      exit 3
    fi
  fi
done
echo "=== r107e-insitu complete $(date -u +%H:%M:%SZ) ==="
