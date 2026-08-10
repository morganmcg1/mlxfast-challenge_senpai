#!/bin/bash
# Arm G rung 1b A/B rig: paired decode-step timing for the norm-fused gate
# softplus kernel. One worker process per arm because DARKBLOOM_* knobs are
# read once at process start.
#
# Usage: research/nezuko_armg_ab.sh <block> <arm> [<arm> ...]
#   arm C = candidate (fused norm hosted in gate_sp, default ON)
#   arm A = control   (DARKBLOOM_NORM_FUSED_GATE_SP=0, stock rmsbfloat16)
#
# Position 0 is a discarded warm-up. Give an ABBA/CAAC-balanced order so
# thermal drift cancels.
set -u
cd "$(dirname "$0")/.."

BLOCK="${1:?block name required}"
shift
OUT="research/armg-runs/${BLOCK}"
mkdir -p "${OUT}"
STEPS="${ARMG_STEPS:-200}"
MACMON="${HOME}/bin/macmon"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{gpu_temp:.temp.gpu_temp_avg,cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

pos=0
for arm in "$@"; do
  case "${arm}" in
    C) knob="" ;;
    A) knob="DARKBLOOM_NORM_FUSED_GATE_SP=0" ;;
    W) knob="DARKBLOOM_NORM_FUSED_GATE_SP=2" ;;
    N) knob="DARKBLOOM_NORM_FUSED_GATE_SP=3" ;;
    S) knob="DARKBLOOM_NORM_FUSED_GATE_SP=4" ;;
    *) echo "unknown arm ${arm}" >&2; exit 2 ;;
  esac
  tag="$(printf 'p%02d-%s' "${pos}" "${arm}")"
  echo "=== ${BLOCK} ${tag} knob='${knob}' t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  # shellcheck disable=SC2086
  env ${knob} python3 research/decode_probe.py \
      --steps "${STEPS}" \
      --dump-steps "${OUT}/${tag}.steps" \
      --stderr "${OUT}/${tag}.err" \
    > "${OUT}/${tag}.log" 2>&1
  rc=$?
  echo "--- ${tag} rc=${rc}"
  grep -E "teacher-forced|decode steps=|worker up" "${OUT}/${tag}.log" || tail -20 "${OUT}/${tag}.log"
  gzip -f "${OUT}/${tag}.err"
  pos=$((pos + 1))
done
echo "=== ${BLOCK} done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
