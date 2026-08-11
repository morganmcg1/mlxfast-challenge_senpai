#!/usr/bin/env bash
# R125-B: log the ns (simdgroups-per-threadgroup) ladder to W&B.
#
# The logger itself is the R117-C one, reused unchanged except through its
# documented env overrides (REF_ARM / WANDB_TAGS / WANDB_NAME / WANDB_NOTES),
# so the paired block-bootstrap arithmetic behind the published interval is
# byte-identical to the one the advisor already reviewed in #707.
#
# Usage:  research/maple-nezuko-r125b-wandb.sh [ROWS.tsv]
set -u
cd "$(dirname "$0")/.."
ROWS="${1:-/tmp/r125b-certify.tsv}"
export REF_ARM="${REF_ARM:-N2}"
export WANDB_TAGS="${WANDB_TAGS:-r125,nezuko,qkv-tg-granularity,local-submit,paired}"
export WANDB_NAME="${WANDB_NAME:-r125b-qkv-tg-granularity-ladder}"
export WANDB_NOTES="${WANDB_NOTES:-R125-B: decode QKV threadgroups-per-simdgroup ladder at rps=1. N2 (64 thr/TG, shipped geometry) is the reference; N4 and N8 change only the constexpr num_simdgroups. All arms run with DARKBLOOM_DECODE_QKV_GATE_FUSED=0 so every arm shares one grid-append state. Instrument: ./benchmark.sh --local-submit, 1023 scored decode steps, M4 Pro 20-core. No official receipt spent.}"
export WANDB_DIR="${WANDB_DIR:-/tmp/wandb-nezuko-r125b}"
exec python3 research/maple-nezuko-r117c-wandb-log.py "$ROWS"
