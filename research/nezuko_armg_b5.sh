#!/bin/bash
# Arm G rung 1d attribution block. b4 showed arm W (fused kernel recomputes the
# RMS, standalone pre-norm dispatch retained) beating the shipped control by
# 44.7 us/step even though it does strictly more work. Two candidate
# explanations remain entangled in that contrast: the removed `rms -> gate_sp`
# dependency edge, and the ns8r1 geometry the fused kernel uses instead of the
# shipped gate_sp ns2r4 geometry.
#
#   A  control    stock rmsbfloat16 pre-norm + shipped gate_sp (ns2r4)
#   S  geometry   fused kernel at ns8r1 but consuming `normalized` from the
#                 standalone dispatch, i.e. the control topology
#   N  decoupled  fused kernel recomputes the RMS, no `normalized` output
#   W  decoupled  as N but also stores an unread `normalized`
#
# S-A is pure geometry/implementation, N-S is pure edge removal, N-W prices the
# unread 4 KiB store, and N-A is the total shippable delta.
set -u
cd "$(dirname "$0")/.."

research/fern_r93_build_worker.sh || exit 1

ARMG_STEPS="${ARMG_STEPS:-200}" research/nezuko_armg_ab.sh b5 \
  A \
  A S W N \
  S W N A \
  W N A S \
  N A S W \
  N W S A \
  A N W S

echo "=== stats ==="
python3 research/nezuko_armg_stats.py research/armg-runs/b5
