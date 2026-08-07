#!/bin/bash
# PR #204 router-emit marginal-dispatch A/B (research-only).
#
# Times pure teacher-forced decode with research/decode_probe.py while toggling
# only DARKBLOOM_DECODE_ROUTER_EMIT_SINK on a single binary, so the two arms
# differ by exactly the 39 standalone router-top8 dispatches per step.
#
# Arms are interleaved ABBA so a linear thermal/clock drift over the session
# cancels in the paired contrast instead of loading onto one arm.
#
#   research/fern_router_emit_ab.sh OUTDIR STEPS PAIRS
set -u
outdir="$1"; shift
steps="$1"; shift
pairs="$1"; shift
mkdir -p "$outdir"

run_arm() {
  local arm="$1" tag="$2" sink
  case "$arm" in
    A) sink=1 ;;   # emit kernel publishes the router; standalone dispatch gone
    B) sink=0 ;;   # base: stock QMV + standalone router dispatch
    C) sink=2 ;;   # emit kernel runs, standalone dispatch kept (attribution)
  esac
  echo "=== run $tag arm=$arm EMIT_SINK=$sink ===" >&2
  /usr/bin/env MLXFAST_WEIGHTS_PATH=weights \
    DARKBLOOM_DECODE_ROUTER_EMIT_SINK="$sink" \
    python3 research/decode_probe.py \
      --steps "$steps" \
      --stderr "$outdir/$tag.worker.err" \
      --dump-steps "$outdir/$tag.steps.txt" \
    2>&1 | sed "s/^/[$tag] /"
}

# Palindromic block: every arm's mean position within a block is identical, so
# a linear thermal/clock drift cancels for all arms, not just for a pair.
block="${ARMS:-ABBA}"

rc=0
for p in $(seq 1 "$pairs"); do
  i=0
  while [ "$i" -lt "${#block}" ]; do
    arm="${block:$i:1}"
    i=$((i + 1))
    run_arm "$arm" "p${p}r${i}.${arm}" || rc=1
  done
done
exit "$rc"
