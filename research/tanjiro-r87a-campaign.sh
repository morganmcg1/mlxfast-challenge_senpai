#!/bin/bash
# R87-A measurement rig: per-kernel decode census under the MLX dispatch
# profiler, one worker process per arm because every knob is read once at
# process start.
#
# Usage: research/tanjiro-r87a-campaign.sh <block> <arm> [<arm> ...]
#
# Arms:
#   A0   stock            (no knob)
#   PF1  steady prefetch  DARKBLOOM_ROUTED_GATEUP_INPUT_PF=1
#   PF2  preamble         DARKBLOOM_ROUTED_GATEUP_INPUT_PF=2
#   PF3  both             DARKBLOOM_ROUTED_GATEUP_INPUT_PF=3
#   B2   positive control DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS=2
#   B4   positive control DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS=4
#   E0   A2 ceiling       DARKBLOOM_PROBE_ROUTED_EXPERT0_PF=1  (timing only)
#
# Arm order is given by the caller so position balance is explicit in the
# invocation and visible in the result file. Position 0 of every block is a
# discarded warm-up.
set -u
cd "$(dirname "$0")/.."

BLOCK="${1:?block name required}"
shift
OUT="research/r87a-runs/${BLOCK}"
mkdir -p "${OUT}"

STEPS="${R87A_STEPS:-200}"
MACMON="${HOME}/bin/macmon"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{gpu_temp:.temp.gpu_temp_avg,cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power}' \
      2>/dev/null
  else
    echo "no-macmon"
  fi
}

arm_env() {
  case "$1" in
    A0)  echo "" ;;
    PF1) echo "DARKBLOOM_ROUTED_GATEUP_INPUT_PF=1" ;;
    PF2) echo "DARKBLOOM_ROUTED_GATEUP_INPUT_PF=2" ;;
    PF3) echo "DARKBLOOM_ROUTED_GATEUP_INPUT_PF=3" ;;
    B2)  echo "DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS=2" ;;
    B4)  echo "DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS=4" ;;
    E0)  echo "DARKBLOOM_PROBE_ROUTED_EXPERT0_PF=1" ;;
    *)   echo "BAD_ARM" ;;
  esac
}

pos=0
for arm in "$@"; do
  knob="$(arm_env "${arm}")"
  if [ "${knob}" = "BAD_ARM" ]; then
    echo "unknown arm ${arm}" >&2
    exit 2
  fi
  tag="$(printf 'p%02d-%s' "${pos}" "${arm}")"
  echo "=== ${BLOCK} ${tag} knob='${knob}' t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  # shellcheck disable=SC2086
  env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 ${knob} \
    python3 research/decode_probe.py \
      --steps "${STEPS}" --profile --profile-top 44 \
      --stderr "${OUT}/${tag}.err" \
    > "${OUT}/${tag}.log" 2>&1
  rc=$?
  echo "--- ${tag} rc=${rc}"
  tail -60 "${OUT}/${tag}.log"
  gzip -f "${OUT}/${tag}.err"
  pos=$((pos + 1))
done
echo "=== ${BLOCK} done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
