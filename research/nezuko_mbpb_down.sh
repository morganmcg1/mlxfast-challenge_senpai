#!/bin/bash
# PR #44 r3 deliverable A: one profiled session, one binary, mirror-balanced,
# extending the MLX_MAX_MB_PER_BUFFER profile sweep DOWNWARD from the shipped
# 200 and including 400 as an in-session upward anchor.
#
# The question is whether wall - gpu_busy_union ("gap", non-overlapped host
# encode/submit time) ranks the caps the way the three ranked M5 receipts do
# (200 best; 50 -1.608%; 512 -1.164%), where M4 wall gets the downward branch
# backwards. Decision rule is pre-registered in
# research/nezuko-mbcap-down-prereg.md and committed before this runs.
#
# Design: warm-up arm discarded, then F R R F over the six levels, so every
# level has the same mean position in the session and linear drift cancels.
# Same binary, same STEPS, same process recipe for every arm; the profiled
# binary's absolute times must never be pooled with an unprofiled sweep.
#
# The prefill pass at the end is counts only. prefill cb is recovered by
# differencing against the decode arms at the same STEPS, as in
# research/nezuko_mbpb_prefill.sh.
set -u
cd "$(dirname "$0")/.."

LOG="research/nezuko-mbpb-down.log"
STEPS="${STEPS:-120}"

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -2 | tee -a "${LOG}" || exit 1

MACMON="${HOME}/bin/macmon"
thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

arm() {
  local mb="$1" mode="$2" tag="$3"
  local extra=""
  [ "${mode}" = "prefill" ] && extra="--prefill"
  echo "=== cap=${mb} mode=${mode} tag=${tag} steps=${STEPS} t=$(date -u +%H:%M:%S) thermal=$(thermal)" \
    | tee -a "${LOG}"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=200 \
      DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
    python3 research/decode_probe.py --steps "${STEPS}" ${extra} --profile \
      --profile-top 0 --stderr "/tmp/nezuko-down-${mode}-mb${mb}-${tag}.err" 2>/dev/null \
    | grep -E "profile:|per steady step|divergence|prefill 512|mlx_peak_gb|decode steps=" \
    | sed "s/^/cap=${mb} ${mode} ${tag} /" | tee -a "${LOG}"
}

echo "======== r3 down sweep start $(date -u +%Y-%m-%dT%H:%M:%SZ) STEPS=${STEPS}" | tee -a "${LOG}"

# Discarded warm-up: first process of a session pays page-in and pipeline warm.
arm 200 decode warmup-discard

for pass in p1 p2 p3 p4; do
  case "${pass}" in
    p1|p4) LEVELS="12 25 50 100 200 400" ;;
    p2|p3) LEVELS="400 200 100 50 25 12" ;;
  esac
  for mb in ${LEVELS}; do
    arm "${mb}" decode "${pass}"
  done
done

# Counts only: prefill cb per 512-token forward, by differencing.
for mb in 12 25 50 100 200 400; do
  arm "${mb}" prefill counts
done

echo "======== r3 down sweep done $(date -u +%Y-%m-%dT%H:%M:%SZ) thermal=$(thermal)" | tee -a "${LOG}"
