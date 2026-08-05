#!/bin/bash
# Research-only. A/B the shared gate/up QMV depth-1 weight staging (A1) and the
# packed cross-lane reduction (A2) against the shipped kernels.
#
#   research/sweep_shared_qmv_staging.sh <split> [steps] [arm ...]
#
# split=1 gives one dispatch per command buffer, so each GPUPROF record times a
# single kernel and the per-dispatch us/call difference isolates the kernel body.
# split=0 keeps the shipped batching for a low-noise per-step wall and
# gpu_busy_union.
cd "$(dirname "$0")/.." || exit 1
SPLIT="${1:-1}"
STEPS="${2:-150}"
shift 2 2>/dev/null
ARMS=("$@")
if [ ${#ARMS[@]} -eq 0 ]; then
    ARMS=(base st pk k1)
fi

for arm in "${ARMS[@]}"; do
    case "$arm" in
        base) stage=0; pack=0 ;;
        st)   stage=1; pack=0 ;;
        pk)   stage=0; pack=1 ;;
        k1)   stage=1; pack=1 ;;
        *) echo "unknown arm ${arm}"; exit 1 ;;
    esac
    echo "================ arm=${arm} STAGE=${stage} PACK=${pack} SPLIT=${SPLIT} ================"
    err="/tmp/qmvstage.${arm}.split${SPLIT}.err"
    DARKBLOOM_SHARED_QMV_STAGE="${stage}" \
    DARKBLOOM_SHARED_QMV_PACK2="${pack}" \
    DARKBLOOM_GPU_PROFILE=1 \
    DARKBLOOM_GPU_PROFILE_SPLIT="${SPLIT}" \
        python3 research/decode_probe.py --steps "${STEPS}" --profile \
            --profile-top 60 --stderr "${err}" 2>&1 \
        | grep -Ev "^ *$" \
        | grep -E 'worker up|divergences|decode steps=|per steady step|profile:|swiglu_qmv_rows1|down_residual|first 8 steps|^ +[0-9]+\.[0-9]'
    grep -E '^GPUPSO .*(swiglu_qmv_rows1|down_residual)' "${err}" \
        | sed 's/^/    /'
    echo
done
echo SWEEP_DONE
