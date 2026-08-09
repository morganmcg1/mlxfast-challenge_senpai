#!/bin/bash
# Discriminating test: is the injected-work instrument alive on the current
# tree's decode path at all? The DRAM sweep reads 256 MiB per dispatch, so even
# one per step must be unmissable. If the sweep moves decode time and the empty
# dispatches do not, the call site is live and the empty dispatches are simply
# free; if neither moves, the call site is dead on this tree.
set -u
OUT="/tmp/r93/liveness"
mkdir -p "$OUT"

run() {
  local tag="$1"; shift
  env "$@" python3 research/decode_probe.py --steps 60 \
    --stderr "${OUT}/worker-${tag}.err" > "${OUT}/${tag}.log" 2>&1
  echo "=== ${tag} rc=$? env=$*"
  grep -E "teacher-forced|^decode steps=" "${OUT}/${tag}.log" || tail -3 "${OUT}/${tag}.log"
}

run base
run sweep1 DARKBLOOM_INJECT_DECODE_SWEEPS=1
run empty2000 DARKBLOOM_INJECT_DECODE_EMPTY=2000 DARKBLOOM_INJECT_EMPTY_TG=8
run empty2000tg160 DARKBLOOM_INJECT_DECODE_EMPTY=2000
run prefempty2000 DARKBLOOM_INJECT_PREFILL_EMPTY=2000 DARKBLOOM_INJECT_EMPTY_TG=8
echo "done $(date -u +%H:%M:%SZ)"
