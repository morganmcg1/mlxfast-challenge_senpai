#!/bin/bash
# Research-only: PR #101 arm A round 3 — high-power drift-balanced ABBA on the
# single geometry the isolated microbenchmark says should win.
#
# research/pr101-gatesp-dispatch-bench.txt measures R1NS2 at 3.466 us/dispatch
# (h64) and 4.013 us (h48) against stock R4NS2 at 5.561 / 4.958, i.e. a 43 %
# cut in isolated serialised execution time, worth 30*(5.561-3.466) +
# 10*(4.958-4.013) = 72.4 us on an ~8.28 ms step = -0.87 %. The 9-point sweep
# measured -0.03 % for the same geometry, but at 160 steps x 2 rounds it could
# not resolve -0.87 % against the host's ~+-0.5 % between-process floor.
#
# Eight 400-step runs in ABBA ABBA order give four replicates per condition and
# cancel linear drift twice, which is the same design that dissolved arm B's
# apparent round-1 win.
set -u
cd "$(dirname "$0")/.."
OUT=research/pr101-gatesp-abba
mkdir -p "$OUT"
STEPS="${STEPS:-400}"

run_point() {
  local tag="$1"; shift
  local log="$OUT/$tag.txt"
  echo "=== $tag steps=$STEPS ($*) ==="
  env "$@" python3 research/decode_probe.py --steps "$STEPS" \
      --dump-steps "$OUT/$tag.steps.txt" \
      --stderr "$OUT/$tag.worker.err" >"$log" 2>&1
  echo "exit=$?"
  grep -E 'divergence|^decode steps' "$log"
}

i=0
for cond in A B B A A B B A; do
  i=$((i + 1))
  if [ "$cond" = A ]; then
    run_point "$(printf 'g%02d_stock_r4n2' "$i")" \
      DARKBLOOM_GATESP_R=4 DARKBLOOM_GATESP_NS=2
  else
    run_point "$(printf 'g%02d_cand_r1n2' "$i")" \
      DARKBLOOM_GATESP_R=1 DARKBLOOM_GATESP_NS=2
  fi
done
