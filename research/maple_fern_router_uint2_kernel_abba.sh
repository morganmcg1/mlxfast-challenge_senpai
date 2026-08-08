#!/bin/bash
# Research-only (PR #442): interleaved per-kernel A/B driver for the routed-QMV
# router Top-8 `uint2 simd_shuffle_xor` packing (`DARKBLOOM_ROUTER_UINT2_SHUFFLE`).
#
# One worker process per arm, ABBA order inside every rep, so process-level
# drift cannot line up with the arm labels. `DARKBLOOM_GPU_PROFILE_SPLIT=1` puts
# one dispatch in each command buffer, which is what makes a sub-microsecond
# per-call effect on `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
# visible; end-to-end decode wall time (MDE +-0.73 %) cannot resolve it.
#
# Arms (all numerically identical, see the guard in LagunaRuntimeModel.swift):
#   off  two scalar simd_shuffle_xor per butterfly stage (default)
#   on   one uint2 simd_shuffle_xor per butterfly stage
#   ctl  invariant control: byte-different, IR-identical copy of `off`
#
#   REPS=3 STEPS=33 ORDER="off on ctl ctl on off" OUT=/tmp/maple-fern-router \
#     bash research/maple_fern_router_uint2_kernel_abba.sh
#
# The worker binary must already carry research/nezuko-pr158-gpuprof-hook.patch.
set -u
STEPS=${STEPS:-33}
REPS=${REPS:-3}
OUT=${OUT:-/tmp/maple-fern-router-uint2}
ORDER=${ORDER:-"off on ctl ctl on off"}
PROBE_ARGS=${PROBE_ARGS:-}
mkdir -p "$OUT"

idx=0
for rep in $(seq 1 "$REPS"); do
  for arm in $ORDER; do
    idx=$((idx + 1))
    tag=$(printf "%02d-rep%s-%s" "$idx" "$rep" "$arm")
    unset DARKBLOOM_ROUTER_UINT2_SHUFFLE
    case "$arm" in
      on) export DARKBLOOM_ROUTER_UINT2_SHUFFLE=1 ;;
      ctl) export DARKBLOOM_ROUTER_UINT2_SHUFFLE=control ;;
    esac
    echo "=== $tag ==="
    DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
      python3 research/decode_probe.py --steps "$STEPS" --profile \
        --profile-top 6 --stderr "$OUT/$tag.err" $PROBE_ARGS \
        >"$OUT/$tag.log" 2>&1
    status=$?
    grep -E "teacher-forced|per steady step" "$OUT/$tag.log"
    echo "exit=$status"
    [ "$status" -eq 0 ] || exit "$status"
  done
done
echo "logs in $OUT"
