#!/bin/bash
# Test the mechanism behind the free region in the dispatch-cost curve.
#
# Hypothesis: the injected chain shares no buffers with model tensors, so MLX
# inserts no ordering between them and the tiny hazard-free command buffers are
# absorbed into gaps in the decode step. Forcing MLX to put everything in one
# enormous command buffer removes the per-command-buffer boundary that lets
# them float, so the same K should start costing real time.
set -u
OUT="/tmp/r93/hazard"
mkdir -p "$OUT"

for mode in default bigbuf; do
  for k in 0 240 800; do
    tag="${mode}-K${k}"
    if [ "$mode" = bigbuf ]; then
      env MLX_MAX_OPS_PER_BUFFER=1000000 MLX_MAX_MB_PER_BUFFER=1000000 \
          DARKBLOOM_INJECT_DECODE_EMPTY="$k" DARKBLOOM_INJECT_EMPTY_TG=8 \
          python3 research/decode_probe.py --steps 120 \
          --stderr "${OUT}/w-${tag}.err" > "${OUT}/${tag}.log" 2>&1
    else
      env DARKBLOOM_INJECT_DECODE_EMPTY="$k" DARKBLOOM_INJECT_EMPTY_TG=8 \
          python3 research/decode_probe.py --steps 120 \
          --stderr "${OUT}/w-${tag}.err" > "${OUT}/${tag}.log" 2>&1
    fi
    echo "=== ${tag} rc=$?"
    grep -E "teacher-forced|^decode steps=" "${OUT}/${tag}.log" \
      || tail -3 "${OUT}/${tag}.log"
  done
done

echo "done $(date -u +%H:%M:%SZ)"
