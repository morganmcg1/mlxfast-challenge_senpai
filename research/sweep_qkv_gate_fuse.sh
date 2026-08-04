#!/bin/bash
# A/B the fused decode QKV+per-head-gate dispatch against the split baseline.
# SPLIT=1 arms give per-dispatch us/call; SPLIT=0 arms give low-noise
# per-step wall / gpu_busy_union so the end-to-end verdict is not perturbed
# by per-dispatch command-buffer boundaries.
cd "$(dirname "$0")/.." || exit 1
for split in 1 0; do
    for fuse in 1 0; do
        echo "================ FUSE=${fuse} SPLIT=${split} ================"
        DARKBLOOM_QKV_GATE_FUSE="${fuse}" \
        DARKBLOOM_GPU_PROFILE=1 \
        DARKBLOOM_GPU_PROFILE_SPLIT="${split}" \
            python3 research/decode_probe.py --steps 120 --profile --profile-top 10 \
                --stderr "/tmp/decode_probe.fuse${fuse}.split${split}.err" 2>&1 \
            | grep -Ev "^ *$"
        echo
    done
done
echo SWEEP_DONE
