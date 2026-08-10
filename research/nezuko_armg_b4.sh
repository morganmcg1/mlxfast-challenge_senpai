#!/bin/bash
# Arm G rung 1c attribution block: decompose the measured regression of the
# norm-fused gate_sp kernel into added prologue work and the new
# `gate_sp -> QKV` dependency edge.
#
#   A  control     stock rmsbfloat16 pre-norm, stock gate_sp
#   W  work-only   fused kernel runs and stores `normalized`, but the pre-norm
#                  dispatch stays and QKV still consumes its output, so gate_sp
#                  is not pulled onto the QKV critical path
#   C  candidate   fused kernel is the sole producer of `normalized`
#
# A-W isolates the added work; W-C isolates the deleted dispatch net of the new
# dependency edge. Six replicates per arm in a drift-balanced order.
set -u
cd "$(dirname "$0")/.."

research/fern_r93_build_worker.sh || exit 1

ARMG_STEPS="${ARMG_STEPS:-200}" research/nezuko_armg_ab.sh b4 \
  C \
  A C W \
  W C A \
  C A W \
  W A C \
  A W C \
  C W A

echo "=== stats ==="
python3 research/nezuko_armg_stats.py research/armg-runs/b4
