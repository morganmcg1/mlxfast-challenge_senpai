#!/bin/bash
# Research-only (PR #301): interleaved per-kernel A/B driver for the shared
# NVFP4 SwiGLU QMV K-block prefetch (`DARKBLOOM_SHARED_QMV_PREFETCH`).
#
# One worker process per arm, ABBA order inside every rep, so process-level
# drift cannot line up with the arm labels. `DARKBLOOM_GPU_PROFILE_SPLIT=1`
# puts one dispatch in each command buffer, which is what makes the ~0.7 us
# per-call effect on `laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1` visible;
# end-to-end decode wall time cannot resolve it.
#
#   REPS=3 STEPS=33 OUT=/tmp/maple-shared-qmv \
#     bash research/maple_shared_qmv_prefetch_abba.sh
#
# The worker binary must already carry research/nezuko-pr158-gpuprof-hook.patch.
set -u
STEPS=${STEPS:-33}
REPS=${REPS:-3}
OUT=${OUT:-/tmp/maple-shared-qmv}
ORDER=${ORDER:-"off on on off"}
mkdir -p "$OUT"

idx=0
for rep in $(seq 1 "$REPS"); do
  for arm in $ORDER; do
    idx=$((idx + 1))
    tag=$(printf "%02d-rep%s-%s" "$idx" "$rep" "$arm")
    unset DARKBLOOM_SHARED_QMV_PREFETCH DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES \
      DARKBLOOM_SHARED_SCALE_HALVED
    case "$arm" in
      on) export DARKBLOOM_SHARED_QMV_PREFETCH=1 ;;
      # Implies the prefetch arm; the header fix-up lives in its prologue.
      pairwise) export DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES=1 ;;
      # PR #443: the same halved plane on the default (non-prefetch) schedule.
      halved) export DARKBLOOM_SHARED_SCALE_HALVED=1 ;;
    esac
    echo "=== $tag ==="
    DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
      python3 research/decode_probe.py --steps "$STEPS" --profile \
        --profile-top 6 --stderr "$OUT/$tag.err" \
        >"$OUT/$tag.log" 2>&1
    status=$?
    grep -E "teacher-forced|per steady step" "$OUT/$tag.log"
    echo "exit=$status"
    [ "$status" -eq 0 ] || exit "$status"
  done
done
echo "logs in $OUT"
