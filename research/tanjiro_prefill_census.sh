#!/usr/bin/env bash
# PR270 non-MoE prefill census driver (research-only; requires the LOCAL-ONLY
# GPUPROF hook from research/pr91-gpuprof-hook.patch to be applied and built).
#
# SPLIT=1 gives per-dispatch family attribution; SPLIT=0 gives the shipped
# command-buffer batching, i.e. the honest wall/busy/gap totals. Both are
# needed: SPLIT=0 alone mis-attributes families by up to 7.6x.
set -u
cd "$(dirname "$0")/.."
OUT=research/pr270-logs
mkdir -p "$OUT"

export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
export DARKBLOOM_GPU_PROFILE=1

for SPLIT in 1 0; do
  echo "=============== SPLIT=${SPLIT} ==============="
  DARKBLOOM_GPU_PROFILE_SPLIT="${SPLIT}" \
    python3 research/prefill_probe.py \
      --reps 6 --profile --profile-top 60 \
      --stderr "${OUT}/split${SPLIT}.worker.err" \
      2>&1 | tee "${OUT}/split${SPLIT}.log"
  echo "exit=${PIPESTATUS[0]}"
done
