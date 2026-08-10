#!/bin/bash
# Research-only driver for the round-107-F Stage 1 down-residual twin probe.
# `run_job` passes argv only, so every knob is a positional argument here.
#
#   research/maple_frieren_r107f_stage1_run.sh SUFFIX ROUNDS DISCARD FOCUS_ROUNDS FOCUS_DISCARD
set -uo pipefail

SUFFIX="${1:-full}"
ROUNDS="${2:-61}"
DISCARD="${3:-6}"
FOCUS_ROUNDS="${4:-201}"
FOCUS_DISCARD="${5:-10}"

cd "$(dirname "$0")/.."
OUTDIR="research/artifacts/maple-frieren-r107f/stage1"
mkdir -p "$OUTDIR"

xcrun swiftc -O research/maple_frieren_r107f_t2d_probe.swift -o /tmp/r107f_probe || exit 2

sysctl -n machdep.cpu.brand_string
pmset -g | grep -E 'powermode' || true

export R107F_ROUNDS="$ROUNDS"
export R107F_DISCARD="$DISCARD"
export R107F_FOCUS_ROUNDS="$FOCUS_ROUNDS"
export R107F_FOCUS_DISCARD="$FOCUS_DISCARD"
export R107F_JSON_OUT="$OUTDIR/t2d-probe-$SUFFIX.json"
exec /tmp/r107f_probe
