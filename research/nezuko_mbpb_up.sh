#!/bin/bash
# Deliverable B1 (r2): command buffers per decode step and per 512-token
# prefill at MLX_MAX_MB_PER_BUFFER levels ABOVE the shipped 200, with
# MLX_MAX_OPS_PER_BUFFER pinned at 200.
#
# Counts only. Boundary counts are a deterministic function of the op stream and
# its byte counts, so they transfer M4 -> M5 exactly (M4 TRANSFER LAW, PR #44);
# boundary *timing* does not, so no balanced blocks or replicates are run here
# and the wall-clock numbers printed below are NOT a verdict. The LOCAL-ONLY
# GPUPROF hooks in device.cpp inflate absolute times.
#
# prefill cb count is recovered by differencing, exactly as in
# research/nezuko_mbpb_prefill.sh:
#   cbs_prefill(cap) = total_with_prefill(cap) - total_without_prefill(cap)
set -u
cd "$(dirname "$0")/.."

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -2 || exit 1

MACMON="${HOME}/bin/macmon"
thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

STEPS="${STEPS:-100}"
CAPS="${CAPS:-200 400 512 1024 2048}"

for mb in ${CAPS}; do
  for mode in decode prefill; do
    extra=""
    [ "${mode}" = "prefill" ] && extra="--prefill"
    echo "=== cap=${mb} mode=${mode} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
    env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=200 \
        DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
      python3 research/decode_probe.py --steps "${STEPS}" ${extra} --profile \
        --profile-top 0 --stderr "/tmp/nezuko-up-${mode}-mb${mb}.err" 2>/dev/null \
      | grep -E "profile:|per steady step|divergence|prefill 512|peak_ram_gb=" \
      | sed "s/^/cap=${mb} ${mode} /"
  done
done

echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
