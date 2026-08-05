#!/bin/bash
# Deliverable B, phase 2 (diagnostics only): command buffers per decode step,
# GPU-busy union, and host gap at each MLX_MAX_MB_PER_BUFFER level.
#
# The wall-clock verdict already lives in research/nezuko-mbpb-levels.log. This
# pass exists only to attribute that verdict, so it runs with the LOCAL-ONLY
# GPU dispatch profiler compiled into device.cpp. That profiler is reverted
# before the submitted surface is reported, and its fputs-per-command-buffer
# cost means the absolute times here must never be compared with phase 1.
#
# DARKBLOOM_GPU_PROFILE_SPLIT=0 keeps MLX's shipped batching policy, so command
# buffer boundaries are exactly the ones the byte cap produces.
set -u
cd "$(dirname "$0")/.."

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -3 || exit 1

MACMON="${HOME}/bin/macmon"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
      2>/dev/null
  else
    echo "no-macmon"
  fi
}

profile_arm() {
  local mb="$1"
  echo "=== profile mb=${mb} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=200 \
      DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
    python3 research/decode_probe.py --steps 200 --profile --profile-top 8 \
      --stderr "/tmp/nezuko-prof-mb${mb}.err" 2>/dev/null
}

for level in 200 100 50 25 12; do
  profile_arm "${level}"
done

echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
