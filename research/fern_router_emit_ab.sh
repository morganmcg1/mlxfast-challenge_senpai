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
  [ "$arm" = "A" ] && sink=1 || sink=0
  echo "=== run $tag arm=$arm EMIT_SINK=$sink ===" >&2
  /usr/bin/env MLXFAST_WEIGHTS_PATH=weights \
    DARKBLOOM_DECODE_ROUTER_EMIT_SINK="$sink" \
    python3 research/decode_probe.py \
      --steps "$steps" \
      --stderr "$outdir/$tag.worker.err" \
      --dump-steps "$outdir/$tag.steps.txt" \
    2>&1 | sed "s/^/[$tag] /"
}

rc=0
for p in $(seq 1 "$pairs"); do
  # ABBA within each block of four runs.
  run_arm A "p${p}r1.A" || rc=1
  run_arm B "p${p}r2.B" || rc=1
  run_arm B "p${p}r3.B" || rc=1
  run_arm A "p${p}r4.A" || rc=1
done
exit "$rc"
