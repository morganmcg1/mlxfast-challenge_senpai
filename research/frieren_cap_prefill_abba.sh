#!/bin/bash
# Position-balanced ABBA screen of the command-buffer byte cap on the PREFILL
# axis. Same arms and design as research/frieren_cap_abba.sh:
#   A = shipped 200 MiB / 400 ops (no MLX_MAX_* in the environment)
#   B = candidate 50 MiB / 400 ops
# The cap is a single process-wide value read once in MLX's device constructor
# (device.cpp:596-597, cached in a function-local static at utils.h:178-187), so
# it cannot be phase-specific: a decode win must be paid for out of prefill if
# prefill regresses. Prefill carries the hard 0.95 floor and elasticity 0.362.
#
# Each arm reports the warm median of 12 identical 512-token prefill forwards
# against a fresh cache, restated as a `wall_ms_per_step` line so
# research/frieren_cap_stats.py can analyse it unchanged.
set -u
cd "$(dirname "$0")/.."

MACMON="${HOME}/bin/macmon"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

run_arm() {
  local name="$1" arm="$2" out=""
  echo "=== ${name} arm=${arm} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  if [ "${arm}" = "A" ]; then
    out=$(env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      python3 research/prefill_probe.py --reps 12 \
        --stderr "/tmp/frcap-prefill-${name}.err" 2>&1)
  else
    out=$(env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER=50 MLX_MAX_OPS_PER_BUFFER=400 \
      python3 research/prefill_probe.py --reps 12 \
        --stderr "/tmp/frcap-prefill-${name}.err" 2>&1)
  fi
  echo "${out}" | grep -E "^prefill (warm median|[0-9]+:)" | tail -13
  local med
  med=$(echo "${out}" | sed -n 's/^prefill warm median: \([0-9.]*\) ms.*/\1/p')
  echo "[${name}-${arm}] steps=12 wall_ms_per_step=${med}"
}

run_arm p00-discard A
run_arm p01 A
run_arm p02 B
run_arm p03 B
run_arm p04 A
run_arm p05 B
run_arm p06 A
run_arm p07 A
run_arm p08 B
run_arm p09 A
run_arm p10 B
run_arm p11 B
run_arm p12 A
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
