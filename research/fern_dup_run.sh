#!/bin/bash
# PR #218 duplicate-injection instrument: one probe arm (research-only).
#
# Runs research/decode_probe.py against the already-built worker with the
# LagunaDecodeDup knobs supplied positionally, so a caller that cannot set
# environment variables (run_training) can still drive every arm.
#
#   fern_dup_run.sh OUTDIR TAG TARGET K STEPS FAULT VERBOSE PROFILE
#
# FAULT/VERBOSE/PROFILE are 0/1. PROFILE=1 requires a GPUPROF hook patch to be
# applied and the worker rebuilt; it perturbs timing and is for census runs only.
set -u
outdir="$1"; tag="$2"; target="$3"; k="$4"; steps="$5"
fault="$6"; verbose="$7"; profile="$8"; shift 8
mkdir -p "$outdir"

extra=()
[ "$profile" = "1" ] && extra+=(--profile --profile-top 60)

/usr/bin/env MLXFAST_WEIGHTS_PATH=weights \
  DARKBLOOM_DECODE_DUP_TARGET="$target" \
  DARKBLOOM_DECODE_DUP_K="$k" \
  DARKBLOOM_DECODE_DUP_FAULT="$fault" \
  DARKBLOOM_DECODE_DUP_VERBOSE="$verbose" \
  DARKBLOOM_GPU_PROFILE="$profile" \
  python3 research/decode_probe.py \
    --steps "$steps" \
    --stderr "$outdir/$tag.worker.err" \
    --dump-steps "$outdir/$tag.steps.txt" \
    "${extra[@]}" "$@" 2>&1 | tee "$outdir/$tag.log" | sed "s/^/[$tag] /"
exit "${PIPESTATUS[0]}"
