#!/usr/bin/env bash
# R86-B gate 1: profiled dispatch + command-buffer counts at every ladder rung.
# Requires the local-only GPUPROF hook in
# Vendor/mlx-swift/.../metal/device.cpp (research/nezuko-pr158-gpuprof-hook.patch).
# Revert that hook and rebuild before any timing run.
#
#   bash research/nezuko_r86b_census.sh /tmp/r86b/census [STEPS]
set -uo pipefail
OUT="${1:?outdir}"
STEPS="${2:-40}"
ARMS="${ARMS:-off w0 w2 w16 t0 t2 t16}"
mkdir -p "${OUT}"

for arm in ${ARMS}; do
  echo "=== $(date -u +%H:%M:%S) ${arm}"
  if [[ "${arm}" == off ]]; then
    DARKBLOOM_GPU_PROFILE=1 \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      > "${OUT}/${arm}.log" 2>&1
  else
    case "${arm:0:1}" in w) mode=wide ;; t) mode=tiny ;; esac
    DARKBLOOM_GPU_PROFILE=1 \
    DARKBLOOM_R86_MODE="${mode}" \
    DARKBLOOM_R86_INSERTS="${arm:1}" \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      > "${OUT}/${arm}.log" 2>&1
  fi
  grep -E "divergence|per steady step|command buffers total|WINDOW" "${OUT}/${arm}.log" | head -4
done
echo "=== $(date -u +%H:%M:%S) census done"
