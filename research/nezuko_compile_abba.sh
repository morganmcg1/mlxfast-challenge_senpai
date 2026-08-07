#!/usr/bin/env bash
# Research-only ABBA runner for the compiled-elementwise-fusion price probe.
#
#   bash research/nezuko_compile_abba.sh <outdir> <blocks> <steps>
#
# Each block runs C,U,U,C so linear host drift cancels within the block. Every
# run is its own worker process; only one model-holding process exists at a
# time.
set -uo pipefail

OUTDIR="${1:?outdir}"
BLOCKS="${2:-4}"
STEPS="${3:-200}"
mkdir -p "${OUTDIR}"

run_arm() {
  local arm="$1" tag="$2"
  case "${arm}" in
    C) export DARKBLOOM_FUSED_ROUTER=0 DARKBLOOM_COMPILED_ROUTER_TAIL=1 ;;
    U) export DARKBLOOM_FUSED_ROUTER=0 DARKBLOOM_COMPILED_ROUTER_TAIL=0 ;;
    B) unset DARKBLOOM_FUSED_ROUTER DARKBLOOM_COMPILED_ROUTER_TAIL ;;
  esac
  python3 research/nezuko_compile_probe.py \
    --steps "${STEPS}" --label "${tag}" \
    --out "${OUTDIR}/${tag}.json" --stderr "${OUTDIR}/${tag}.err"
}

i=0
run_seq() {
  i=$((i + 1))
  run_arm "$1" "$(printf 's%02d_%s' "${i}" "$1")"
}

# B brackets the paired blocks so host drift across the whole session is visible.
run_seq B
for ((b = 1; b <= BLOCKS; b++)); do
  for arm in C U U C; do
    run_seq "${arm}"
  done
done
run_seq B
