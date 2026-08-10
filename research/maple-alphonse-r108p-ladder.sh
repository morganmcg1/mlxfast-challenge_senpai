#!/usr/bin/env bash
# R108-P dispatch-removal-symmetry ladder runner.
#
# Arms are named env sets declared in ARM_ENV below. Every arm runs the same
# binary built from the unmodified r108-p base surface: ladder D turns shipped
# fusions OFF (a real removal measured in reverse) and ladder E injects
# near-empty dispatches. Only encoder dispatch count changes between arms of a
# ladder; arithmetic is fixed by construction for ladder E and audited per rung
# for ladder D.
#
#   SCHEDULE="e0 e276 e276 e0" ./research/maple-alphonse-r108p-ladder.sh s1
set -u

SESSION="${1:?usage: r108p-ladder.sh SESSION}"
OUT="research/artifacts/maple-alphonse-r108p/ladder"
PRECOOL_SECONDS="${PRECOOL_SECONDS:-120}"
SCHEDULE="${SCHEDULE:?set SCHEDULE to a space separated arm list}"

mkdir -p "${OUT}"

# ladder E: injected near-empty dispatches per decode step (arithmetic fixed).
# ladder D: cumulative de-fusion; d0 == e0 == unmodified base.
arm_env() {
  case "$1" in
    e0|d0) printf '' ;;
    e78)   printf 'DARKBLOOM_INJECT_DECODE_EMPTY=78' ;;
    e156)  printf 'DARKBLOOM_INJECT_DECODE_EMPTY=156' ;;
    e198)  printf 'DARKBLOOM_INJECT_DECODE_EMPTY=198' ;;
    e276)  printf 'DARKBLOOM_INJECT_DECODE_EMPTY=276' ;;
    e158)  printf 'DARKBLOOM_INJECT_DECODE_EMPTY=158' ;;
    dR)    printf 'DARKBLOOM_FUSED_ROUTER_CAST=0' ;;
    dQ)    printf 'DARKBLOOM_FUSED_NORM_AFFINE_QKV=0' ;;
    d1)    printf 'DARKBLOOM_FUSED_ROUTER_CAST=0' ;;
    d2)    printf 'DARKBLOOM_FUSED_ROUTER_CAST=0 DARKBLOOM_FUSED_RESIDUAL_RMS=0' ;;
    d3)    printf 'DARKBLOOM_FUSED_ROUTER_CAST=0 DARKBLOOM_FUSED_RESIDUAL_RMS=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0' ;;
    d4)    printf 'DARKBLOOM_FUSED_ROUTER_CAST=0 DARKBLOOM_FUSED_RESIDUAL_RMS=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0 DARKBLOOM_FUSED_ROUTER_NORM=0' ;;
    *)     echo "unknown arm $1" >&2; return 1 ;;
  esac
}

idx=0
consecutive_failures=0
for arm in ${SCHEDULE}; do
  idx=$((idx + 1))
  env_spec="$(arm_env "${arm}")" || exit 1
  tag=$(printf '%s.p%02d.%s' "${SESSION}" "${idx}" "${arm}")
  if [[ -f "${OUT}/${tag}.row.json" ]]; then
    echo "r108p-ladder: ${tag} already present, skipping"
    continue
  fi
  if [[ "${PRECOOL_SECONDS}" -gt 0 ]]; then
    echo "r108p-ladder: precool ${PRECOOL_SECONDS}s before ${tag} $(date -u +%H:%M:%SZ)"
    sleep "${PRECOOL_SECONDS}"
  fi
  ./benchmark.sh --local-cool-gate-only >>"${OUT}/precool.log" 2>&1 || true
  rm -f score.local-iterate.json
  echo "=== ${tag} env='${env_spec}' starting $(date -u +%H:%M:%SZ) ==="
  start=${SECONDS}
  if [[ -z "${env_spec}" ]]; then
    MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-iterate >"${OUT}/${tag}.log" 2>&1
  else
    # shellcheck disable=SC2086
    env ${env_spec} MLXFAST_LOCAL_FAN_PROMPT=0 ./benchmark.sh --local-iterate \
      >"${OUT}/${tag}.log" 2>&1
  fi
  rc=$?
  dur=$((SECONDS - start))
  git checkout -q -- Package.resolved 2>/dev/null || true
  if [[ -f score.local-iterate.json ]]; then
    cp score.local-iterate.json "${OUT}/${tag}.score.json"
    jq -c --arg session "${SESSION}" --arg arm "${arm}" --argjson pos "${idx}" \
      --argjson dur "${dur}" --arg tag "${tag}" --arg envspec "${env_spec}" \
      '{session:$session, pos:$pos, arm:$arm, tag:$tag, env:$envspec, seconds:$dur,
        decode:.metrics.decode_seconds_per_token,
        prefill:.metrics.prefill_seconds_per_token,
        passed:.metrics.passed_correctness, error:.metrics.error}' \
      "${OUT}/${tag}.score.json" > "${OUT}/${tag}.row.json"
    echo "r108p-ladder: $(cat "${OUT}/${tag}.row.json")"
  else
    echo "r108p-ladder: ${tag} rc=${rc} seconds=${dur} NO SCORE FILE"
    tail -25 "${OUT}/${tag}.log"
  fi
  printf '%s rc=%s seconds=%s env=%s\n' "${tag}" "${rc}" "${dur}" "${env_spec}" \
    | tee -a "${OUT}/summary.txt"
  if [[ "${rc}" -eq 0 ]]; then
    consecutive_failures=0
  else
    consecutive_failures=$((consecutive_failures + 1))
    if [[ "${consecutive_failures}" -ge 3 ]]; then
      echo "r108p-ladder: three consecutive failures, aborting" | tee -a "${OUT}/summary.txt"
      exit 1
    fi
  fi
done
echo "r108p-ladder: schedule complete $(date -u +%H:%M:%SZ)"
