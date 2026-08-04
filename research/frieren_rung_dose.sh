#!/bin/bash
# Position-balanced dose-response for the sub-layer decode rungs, at
# ranked-parity settings (full startup profile, shipped 200/400 caps).
#
# The unbalanced screen carried ~0.8% of monotone drift across arm positions
# (controls at positions 1/5/7 measured 9.0356 / 9.1076 / 9.1136), which is
# larger than the effect under test, so each level here occupies positions
# summing to 15 and a linear position effect cancels exactly:
#
#   pos:  1    2   3    4    5    6   7   8    9
#   arm:  off  ab  abc  abc  off  ab  ab  abc  off
#
# Mechanism under test: added command-buffer boundaries reduce GPU-busy time at
# a measured -1.35 us per boundary. Traced arms already give 48 cbs/step at
# `off` and 90 at `ab`; the tenth arm traces `abc` to place it on that line.
# Rung `a` alone measured worse than control and is not tested alone here.
set -u
cd "$(dirname "$0")/.."

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -3 || exit 1

run_arm() {
  local name="$1" rungs="$2" trace="${3:-0}"
  local traceout="/tmp/frcb-dose-${name}.txt"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      DARKBLOOM_DECODE_SUBLAYER_ASYNC="${rungs}" \
      FRIEREN_CBPROF="${trace}" \
    python3 research/frieren_host_cpu_probe.py \
      --warmup-steps 60 --measure-steps 2000 --label "${name}" 2>"${traceout}"
  if [ "${trace}" = "1" ]; then
    echo "--- trace analysis ${name} ---"
    python3 research/frieren_head_region.py "${traceout}" 2>&1 | \
      grep -E "steady steps|step period|GPU idle total|GPU busy fraction|command buffers per step|\(1\) |\(2\) "
  fi
}

run_arm p1-off off
run_arm p2-ab ab
run_arm p3-abc abc
run_arm p4-abc abc
run_arm p5-off off
run_arm p6-ab ab
run_arm p7-ab ab
run_arm p8-abc abc
run_arm p9-off off
run_arm p10-trace-abc abc 1
