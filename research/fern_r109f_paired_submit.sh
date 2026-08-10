#!/usr/bin/env bash
# R109-F integration: interleaved paired ./benchmark.sh --local-submit across
# pre-staged worker labels.
#
# Why interleave rather than block: the R109-F Stage 0 baseline family showed a
# reproducible cold-start penalty on replicate 1 of a session (decode +0.746%,
# prefill +1.068% versus the steady-state median) that is larger than the whole
# 0.378% ranked bar. A blocked design charges that penalty entirely to whichever
# arm runs first. So every arm appears at several positions in ORDER, and the
# first slot of the session is a warmup label that the analyser discards.
#
# Usage: ORDER="W B C B C B C B C" LABELS="B=cand,C=base,W=base" \
#          research/fern_r109f_paired_submit.sh
#
# ORDER   whitespace-separated arm letters, executed in that order.
# LABELS  comma-separated arm=stagedlabel map. Every letter in ORDER must map.
# TAG     artifact prefix (default "paired").
# ROOT    staging root (default .build-worker/arms), see stage_worker.sh. Must
#         stay inside the repo tree; a /tmp staging root is denied by Seatbelt.
#
# A non-zero benchmark exit does not stop the campaign: --local-submit exits 1
# on a failed gate but still writes real seconds-per-token, and a correctness
# failure on one arm is a result to record, not a reason to abandon the pairing.
set -uo pipefail
cd "$(dirname "$0")/.."

ORDER="${ORDER:?ORDER is required}"
LABELS="${LABELS:?LABELS is required, e.g. LABELS=\"A=base,B=cand\"}"
TAG="${TAG:-paired}"
ROOT="${ROOT:-.build-worker/arms}"
OUT="research/artifacts/fern-r109f/paired"
SESSION="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${OUT}"

resolve() {
  local arm="$1" pair
  for pair in ${LABELS//,/ }; do
    if [ "${pair%%=*}" = "${arm}" ]; then
      echo "${pair#*=}"
      return 0
    fi
  done
  return 1
}

# Fail closed before spending an hour of GPU time: an unmapped letter or a
# missing staged binary would otherwise silently fall through to whatever
# .build-worker happens to hold and fabricate a near-zero paired difference.
for arm in ${ORDER}; do
  label="$(resolve "${arm}")" || { echo "FATAL: arm '${arm}' has no LABELS entry" >&2; exit 2; }
  bin="${ROOT}/${label}/mlxfast-runtime-worker"
  [ -x "${bin}" ] || { echo "FATAL: staged worker missing: ${bin}" >&2; exit 2; }
  [ -e "${ROOT}/${label}/mlx.metallib" ] || { echo "FATAL: staged metallib missing for ${label}" >&2; exit 2; }
done
echo "=== ${TAG} session ${SESSION} order '${ORDER}' labels '${LABELS}'"
for arm in $(echo "${ORDER}" | tr ' ' '\n' | sort -u); do
  label="$(resolve "${arm}")"
  echo "--- arm ${arm} -> ${label}: $(grep worker_sha256 "${ROOT}/${label}/PROVENANCE.txt")"
done

export MLXFAST_LOCAL_FAN_PROMPT=0

i=0
for arm in ${ORDER}; do
  i=$((i + 1))
  slot="$(printf '%02d' "${i}")"
  label="$(resolve "${arm}")"
  stem="${OUT}/${TAG}-${SESSION}-${slot}-${arm}"
  stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "=== ${TAG} slot ${slot} arm ${arm} label ${label} start ${stamp} ==="
  MLXFAST_RUNTIME_WORKER_EXECUTABLE="${ROOT}/${label}/mlxfast-runtime-worker" \
  MLXFAST_SCORE_PATH="${stem}.json" \
    ./benchmark.sh --local-submit >"${stem}.log" 2>&1
  rc=$?
  echo "=== ${TAG} slot ${slot} arm ${arm} rc=${rc} end $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  if [ -f "${stem}.json" ]; then
    python3 - "${stem}.json" "${arm}" "${label}" "${rc}" "${stamp}" "${slot}" <<'PY'
import json, sys
path, arm, label, rc, stamp, slot = sys.argv[1:7]
d = json.load(open(path))
m = d.get("metrics", {})
print(json.dumps({
    "slot": slot, "arm": arm, "label": label, "rc": int(rc), "started": stamp,
    "decode_s_per_tok": m.get("decode_seconds_per_token"),
    "prefill_s_per_tok": m.get("prefill_seconds_per_token"),
    "score": d.get("score"), "passed": d.get("passed"),
    "passed_correctness": m.get("passed_correctness"),
    "checked_steps": m.get("checked_steps"),
    "golden_hash": m.get("golden_hash"),
    "first_failing_step": m.get("first_failing_step"),
    "error": m.get("error"),
}))
PY
  else
    echo "{\"slot\": \"${slot}\", \"arm\": \"${arm}\", \"label\": \"${label}\", \"rc\": ${rc}, \"error\": \"no score json\"}"
  fi
done
echo "=== ${TAG} session ${SESSION} complete $(date -u +%Y-%m-%dT%H:%M:%SZ)"
