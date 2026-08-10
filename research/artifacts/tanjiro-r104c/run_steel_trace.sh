#!/usr/bin/env bash
# R104-C: capture ground-truth non-NAX steel GEMM shapes for one 512-token prefill.
# Reuses research/prefill_probe.py (rule 58).
#
# Requires the LOCAL-ONLY darkbloom_steel_trace prints in the non-nax paths of
# Vendor/mlx-swift/.../metal/matmul.cpp. Those prints are reverted before the
# result commit; the submitted tree contains no matmul.cpp change.
set -uo pipefail
cd "$(dirname "$0")/../../.."
OUT=research/artifacts/tanjiro-r104c
mkdir -p "$OUT"
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
export DARKBLOOM_STEEL_TRACE=1
python3 research/prefill_probe.py --reps 1 \
  --stderr "$OUT/steeltrace.worker.err" \
  >"$OUT/steeltrace.log" 2>&1
echo "exit=$?"
grep -c 'darkbloom\]\[steel' "$OUT/steeltrace.worker.err" || true
