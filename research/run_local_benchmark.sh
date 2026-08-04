#!/usr/bin/env bash
# Research-only wrapper (not part of the submission).
#
# This AWS-hosted M4 Pro exposes no GPU die temperature: macmon reports a frozen
# 2.37 C for `.temp.gpu_temp_avg`, which trips the harness plausibility floor and
# fails the cool-down gate before any timed phase. The CPU package sensor on the
# same die is live and varies with load, so the gate keeps its 40 C threshold and
# its wait behaviour through the documented MLXFAST_GPU_TEMP_CMD portability
# seam, reading the sensor that actually works on this host.
#
# Usage: research/run_local_benchmark.sh [--local-iterate|--local-submit]
set -euo pipefail

cd "$(dirname "$0")/.."

export PATH="${HOME}/.local/bin:${HOME}/bin:${PATH}"
export MLXFAST_MACMON_BIN="${MLXFAST_MACMON_BIN:-${HOME}/bin/macmon}"
export MLXFAST_GPU_TEMP_CMD="${MLXFAST_MACMON_BIN} pipe -s1 | jq -M -r '.temp.cpu_temp_avg'"
export MLXFAST_LOCAL_FAN_PROMPT=0

"${MLXFAST_MACMON_BIN}" pipe --samples 3 --interval 500 \
    | jq -M -c '{t: .timestamp, cpu: .temp.cpu_temp_avg, gpu: .temp.gpu_temp_avg, gpu_power, ram: .memory.ram_usage}'

exec ./benchmark.sh "$@"
