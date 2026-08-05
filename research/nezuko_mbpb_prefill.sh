#!/bin/bash
# Deliverable B addendum: command buffers consumed by ONE 512-token prefill at
# each MLX_MAX_MB_PER_BUFFER level, plus the local prefill wall.
#
# decode_probe's --profile window only covers the steady decode steps, so the
# prefill command-buffer count is recovered by differencing total GPUPROF
# records against the matching no-prefill run in
# research/nezuko-mbpb-profile.log:
#
#   cbs_prefill(cap) = total_with_prefill(cap) - total_without_prefill(cap)
#
# Everything else about the two runs is identical (same steps, same worker, same
# seed prefill inside decode_begin), so the difference is exactly the extra
# 512-token prefill request.
set -u
cd "$(dirname "$0")/.."

MACMON="${HOME}/bin/macmon"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

for mb in 200 100 50 25 12; do
  echo "=== prefill-count mb=${mb} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=200 \
      DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
    python3 research/decode_probe.py --steps 200 --prefill --profile \
      --profile-top 0 --stderr "/tmp/nezuko-pref-mb${mb}.err" 2>/dev/null \
    | grep -E "prefill 512|profile:|per steady step|divergence"
done

echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
