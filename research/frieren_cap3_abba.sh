#!/bin/bash
# Three-level, position-balanced screen of the command-buffer byte cap on BOTH
# scored axes, so the single global value that maximises the score can be chosen
# before any official receipt is spent.
#
# Levels (all at ranked parity, DARKBLOOM_STARTUP_MEMORY_PROFILE=full, ops=400):
#   A = 200 MiB  (shipped, LagunaRuntimeWeights.swift:385-389)
#   C = 100 MiB
#   B =  50 MiB  (= MLX's own default for an 's' architecture host)
#
# The cap is process-wide, so decode and prefill must be judged together:
#   score elasticities on the ranked host are 0.638 for T and 0.362 for S.
# Each arm measures both axes in ONE worker process: 16 identical 512-token
# prefill forwards (warm median) followed by 2000 one-token decode steps
# (median), which also halves the model-load overhead versus separate screens.
#
# Positions per level sum to 15, so a linear drift term cancels:
#   pos:  1  2  3  4  5  6  7  8  9
#   arm:  A  B  C  C  A  B  B  C  A
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
  local name="$1" arm="$2" mb="$3" out=""
  echo "=== ${name} arm=${arm} mb=${mb} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  if [ "${arm}" = "A" ]; then
    out=$(env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      python3 research/prefill_probe.py --reps 16 --decode-steps 2000 \
        --stderr "/tmp/frcap3-${name}.err" 2>&1)
  else
    out=$(env DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
        MLX_MAX_MB_PER_BUFFER="${mb}" MLX_MAX_OPS_PER_BUFFER=400 \
      python3 research/prefill_probe.py --reps 16 --decode-steps 2000 \
        --stderr "/tmp/frcap3-${name}.err" 2>&1)
  fi
  local pre dec
  pre=$(echo "${out}" | sed -n 's/^prefill warm median: \([0-9.]*\) ms.*/\1/p')
  dec=$(echo "${out}" | sed -n 's/^decode: \([0-9.]*\) ms\/step.*/\1/p')
  echo "${out}" | grep -E "^(prefill warm median|decode:|peak_ram_gb)"
  echo "[${name}-${arm}] prefill_ms=${pre} decode_ms=${dec}"
}

run_arm p00-discard A 200
run_arm p01 A 200
run_arm p02 B 50
run_arm p03 C 100
run_arm p04 C 100
run_arm p05 A 200
run_arm p06 B 50
run_arm p07 B 50
run_arm p08 C 100
run_arm p09 A 200
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
