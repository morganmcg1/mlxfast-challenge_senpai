#!/bin/bash
# Locate the knee in the injected-dispatch cost curve on the research host.
#
# The first ladder probe found K in {40,120,240} completely free while K=2000
# costs ~1.1 us/dispatch, so the marginal cost of a decode dispatch is not a
# constant: small counts hide inside existing GPU overlap and only larger counts
# are charged. This sweep places the official M5 rungs either side of that knee
# instead of stacking all three inside the free regime.
set -u
OUT="/tmp/r93/knee"
mkdir -p "$OUT"

for k in 0 240 480 800 1200 1600 2400 0; do
  tag="K${k}-$(date -u +%H%M%S)"
  DARKBLOOM_INJECT_DECODE_EMPTY="$k" DARKBLOOM_INJECT_EMPTY_TG=8 \
    python3 research/decode_probe.py --steps 120 \
      --stderr "${OUT}/worker-${tag}.err" > "${OUT}/${tag}.log" 2>&1
  echo "=== K=${k} rc=$? $(date -u +%H:%M:%SZ)"
  grep -E "teacher-forced|^decode steps=" "${OUT}/${tag}.log" || tail -3 "${OUT}/${tag}.log"
done
echo "done $(date -u +%H:%M:%SZ)"
