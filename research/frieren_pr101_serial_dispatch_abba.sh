#!/bin/bash
# Research-only: PR #101 mechanism probe — how much intra-command-buffer
# overlap does the shipped decode path actually exploit?
#
# The #73 census reports gpu_busy_sum == gpu_busy_union on the shipped SPLIT=0
# path and concludes decode concurrency is exactly zero. That equality is
# measured at command-buffer grain: each command buffer contributes one
# [gpuStartTime, gpuEndTime] interval, so the statistic can only detect two
# *command buffers* overlapping. Dispatch-level overlap *inside* one command
# buffer shortens that interval and is invisible to it by construction.
#
# MLX opens every compute encoder with MTL::DispatchTypeConcurrent
# (Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:557-561) and
# inserts memoryBarrier(BarrierScopeBuffers) only on a real RAW/WAR hazard
# (device.cpp:318-375). So consecutive hazard-free dispatches may run
# concurrently. gate_sp is exactly such a case: it reads `normalized`
# (LagunaRuntimeModel.swift:5802-5803), the same tensor the fused QKV dispatch
# reads (:5761-5762), and not the QKV output, so no barrier separates them.
#
# Forcing MTL::DispatchTypeSerial removes all intra-encoder overlap. The
# step-time delta is therefore a direct measurement of the shadow execution the
# census cannot see. Serial dispatch is strictly more conservative than
# concurrent + hazard barriers, so it cannot change results; the divergence
# check confirms that.
set -u
cd "$(dirname "$0")/.."
OUT=research/pr101-serial-dispatch
mkdir -p "$OUT"
STEPS="${STEPS:-400}"

run_point() {
  local tag="$1"; shift
  local log="$OUT/$tag.txt"
  echo "=== $tag steps=$STEPS ($*) ==="
  env "$@" python3 research/decode_probe.py --steps "$STEPS" \
      --dump-steps "$OUT/$tag.steps.txt" \
      --stderr "$OUT/$tag.worker.err" >"$log" 2>&1
  echo "exit=$?"
  grep -E 'divergence|^decode steps' "$log"
}

i=0
for cond in A B B A A B B A; do
  i=$((i + 1))
  if [ "$cond" = A ]; then
    run_point "$(printf 's%02d_concurrent' "$i")" \
      DARKBLOOM_FORCE_SERIAL_DISPATCH=0
  else
    run_point "$(printf 's%02d_serial' "$i")" \
      DARKBLOOM_FORCE_SERIAL_DISPATCH=1
  fi
done
