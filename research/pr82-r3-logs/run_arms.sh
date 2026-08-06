#!/bin/bash
# PR #82 r3 dispatch-order arms. One model-holding process at a time, run
# back to back inside a single supervised process. Counterbalanced core
# (O0 vs Ob, n=3 each) first, exploratory screens last.
set -u
cd "$(dirname "$0")/../.." || exit 1
LOGS=research/pr82-r3-logs

run() { # run <tag> <order-env-or-empty>
  local tag="$1" order="$2"
  echo "=== $tag (DARKBLOOM_DOWN_INPUT_ORDER=${order:-<unset>}) $(date -u +%H:%M:%S) ==="
  if [ -n "$order" ]; then export DARKBLOOM_DOWN_INPUT_ORDER="$order";
  else unset DARKBLOOM_DOWN_INPUT_ORDER; fi
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
    python3 research/decode_probe.py --steps 200 --profile --profile-top 44 \
    --stderr "/tmp/pr82r3_${tag}.err" > "$LOGS/${tag}.txt" 2>&1
  grep -E "divergences|per steady step" "$LOGS/${tag}.txt"
}

run o0_a ""
run ob_a b
run ob_b b
run o0_b ""
run o0_c ""
run ob_c b
run osf_a sf
run oc_a c
run od_a d
echo "=== all arms done $(date -u +%H:%M:%S) ==="
