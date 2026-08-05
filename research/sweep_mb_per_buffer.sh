#!/bin/bash
# MLX_MAX_MB_PER_BUFFER elasticity sweep (deliverable A local proxy).
#
# The ranked >=64 GiB full profile sets MLX_MAX_MB_PER_BUFFER/OPS_PER_BUFFER
# with setenv overwrite=0 (LagunaRuntimeWeights.swift:386-387), so an
# externally supplied value wins. The <64 GiB low-memory profile instead sets
# them with overwrite=1 (RuntimeStartupMemoryPolicy.apply()) to 128 MB / 64
# ops, which is why this sweep forces DARKBLOOM_STARTUP_MEMORY_PROFILE=full:
# that is the only way a sub-64 GiB host can exercise the ranked knob at all.
#
# usage: sweep_mb_per_buffer.sh [steps] [arm...]
#   arm := low            natural low-memory profile (128 MB / 64 ops)
#        | full<MB>       forced full profile, MLX_MAX_MB_PER_BUFFER=<MB>
set -u
cd "$(dirname "$0")/.." || exit 1
STEPS="${1:-150}"
shift || true
ARMS=("$@")
if [ "${#ARMS[@]}" -eq 0 ]; then
  ARMS=(full200 low full50 full200 full400 full200)
fi

for arm in "${ARMS[@]}"; do
  echo
  echo "================ mbpb ${arm} STEPS=${STEPS} ================"
  unset DARKBLOOM_STARTUP_MEMORY_PROFILE MLX_MAX_MB_PER_BUFFER MLX_MAX_OPS_PER_BUFFER
  if [ "${arm}" != "low" ]; then
    mb="${arm#full}"
    export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
    export MLX_MAX_MB_PER_BUFFER="${mb}"
    export MLX_MAX_OPS_PER_BUFFER=200
  fi
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
    python3 research/decode_probe.py \
      --steps "${STEPS}" --profile --profile-top 8 \
      --stderr "/tmp/mbpb.${arm}.err" 2>&1
  echo "arm ${arm} exit=$?"
  grep -m2 -E "startup profile|MB_PER_BUFFER" "/tmp/mbpb.${arm}.err" 2>/dev/null | sed 's/^/  notice: /'
done
echo
echo "SWEEP_DONE"
