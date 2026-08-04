#!/bin/bash
# Sub-layer decode-only asyncEval rung screen, at ranked-parity memory settings.
#
# The cap-50 arm beats the ranked cap-200 arm by ~1.56% on this host, and the
# whole gap is GPU-busy time (8409.6 vs 8533.1 us), not idle. Boundary density
# is 3.5/layer at cap 50 versus 1.2/layer at cap 200, and the existing
# layer-boundary ladder cannot add density because its rungs land where a volume
# cut already happens (ladder1 at cap 200 measured 9.1396 vs 9.1003 control
# mean, i.e. nothing). These arms add 1-2 sub-layer rungs per layer instead.
#
# All arms hold DARKBLOOM_STARTUP_MEMORY_PROFILE=full and the shipped 200/400
# caps, so only DARKBLOOM_DECODE_SUBLAYER_ASYNC varies.
set -u
cd "$(dirname "$0")/.."

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -5 || exit 1

run_arm() {
  local name="$1" rungs="$2" trace="${3:-0}"
  echo "=== arm ${name} rungs=${rungs} trace=${trace} ==="
  local traceout="/tmp/frcb-sublayer-${name}.txt"
  env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      DARKBLOOM_DECODE_SUBLAYER_ASYNC="${rungs}" \
      FRIEREN_CBPROF="${trace}" \
    python3 research/frieren_host_cpu_probe.py \
      --warmup-steps 60 --measure-steps 2000 --tag "${name}" 2>"${traceout}"
  if [ "${trace}" = "1" ]; then
    echo "--- trace analysis ${name} ---"
    python3 research/frieren_head_region.py "${traceout}" 2>&1 | \
      grep -E "steady steps|step period|GPU idle total|GPU busy fraction|command buffers per step|boundaries per step|\(1\) |\(2\) |front idle|dispatches in first cb"
  fi
}

run_arm ctrl-1 off
run_arm rung-a a
run_arm rung-b b
run_arm rung-ab ab
run_arm ctrl-2 off
run_arm rung-ab-2 ab

run_arm trace-ctrl off 1
run_arm trace-ab ab 1
