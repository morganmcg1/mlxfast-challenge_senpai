#!/usr/bin/env bash
# R125-E reachability evidence: which kernels actually run in the decode window,
# at shipped defaults and with DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1.
#
# Timing here is meaningless (GPU profiling perturbs the window); the output of
# interest is the kernel-name list, which decides whether a knob is inert.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
OUT="${OUT:-/tmp/r125e}"
STEPS="${STEPS:-48}"
mkdir -p "${OUT}"

for arm in C FUS; do
  extra=()
  [ "${arm}" = "FUS" ] && extra+=("DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1")
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_GPU_PROFILE=1 "${extra[@]}" \
    python3 research/decode_probe.py --steps "${STEPS}" --profile --profile-top 80 \
      --stderr "${OUT}/trace_${arm}.err" >"${OUT}/trace_${arm}.log" 2>&1
  echo "=== ${arm} rc=$? ==="
  grep -c 'GPUPROF' "${OUT}/trace_${arm}.err"
done
