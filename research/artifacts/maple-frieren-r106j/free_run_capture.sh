#!/bin/bash
# Free-run (greedy continuation) capture for both arms, sequentially.
set -u
cd /Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target

SCRIPT=research/maple-frieren-r106j-margin-certificate.py
STEPS=128

echo "=== ARM 1/2: baseline (stock env), free-run, ${STEPS} steps ==="
env -u DARKBLOOM_QMV_WIDE_CODES \
  python3 "$SCRIPT" capture \
    --label baseline_stock \
    --mode free \
    --steps "$STEPS" \
    --out /tmp/r106j/baseline_free.npz
echo "arm1 exit=$?"

echo "=== ARM 2/2: DARKBLOOM_QMV_WIDE_CODES=1, free-run, ${STEPS} steps ==="
DARKBLOOM_QMV_WIDE_CODES=1 \
  python3 "$SCRIPT" capture \
    --label qmv_wide_codes \
    --mode free \
    --steps "$STEPS" \
    --out /tmp/r106j/wide_free.npz
echo "arm2 exit=$?"

echo "=== done ==="
ls -l /tmp/r106j/
