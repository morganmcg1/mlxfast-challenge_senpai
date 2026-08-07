#!/usr/bin/env bash
# PR270: capture ground-truth non-NAX steel GEMM shapes for one 512-token prefill.
# Requires the LOCAL-ONLY darkbloom_steel_trace prints in the non-nax paths of
# Vendor/mlx-swift/.../metal/matmul.cpp (reverted before submission).
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p research/pr270-logs
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
export DARKBLOOM_STEEL_TRACE=1
python3 research/prefill_probe.py --reps 1 \
  --stderr research/pr270-logs/steeltrace.worker.err \
  >research/pr270-logs/steeltrace.log 2>&1
echo "exit=$?"
grep -c 'darkbloom\]\[steel' research/pr270-logs/steeltrace.worker.err || true
