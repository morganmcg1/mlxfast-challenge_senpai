#!/bin/bash
# A/B the fused down+residual dispatch geometry (rows per simdgroup).
# Each arm runs a fresh worker so weight residency and caches are matched.
cd "$(dirname "$0")/.." || exit 1
for n in "$@"; do
    echo "================ DARKBLOOM_DOWN_ROWS_PER_SIMD=${n} ================"
    DARKBLOOM_DOWN_ROWS_PER_SIMD="${n}" \
    DARKBLOOM_GPU_PROFILE=1 \
    DARKBLOOM_GPU_PROFILE_SPLIT=1 \
        python3 research/decode_probe.py --steps 120 --profile --profile-top 6 \
            --stderr "/tmp/decode_probe.rps${n}.err" 2>&1 \
        | grep -Ev "^ *$"
    echo
done
echo SWEEP_DONE
