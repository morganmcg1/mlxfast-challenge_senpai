#!/bin/bash
# r128-P attribution support: repeated paired samples of the cold timed prefill
# forward (0 warmup, first forward in a fresh worker process) against the warm
# second 512-token forward printed by the decode seed phase, on one named host.
# Research-only; touches no submitted path.
set -u
N="${1:-5}"
OUT="research/artifacts/r128p"
mkdir -p "$OUT"
SUMMARY="$OUT/cold-warm.tsv"
printf 'run\trc\tcold_s_per_tok\twarm_seed_seconds\tdecode_s_per_tok\n' >"$SUMMARY"
for i in $(seq 1 "$N"); do
  log="$OUT/iterate-$i.log"
  ./benchmark.sh --local-iterate >"$log" 2>&1
  rc=$?
  cp -f score.local-iterate.json "$OUT/score-$i.json" 2>/dev/null
  cold=$(grep -o '"prefill_seconds_per_token" : [0-9.e-]*' "$OUT/score-$i.json" | tail -1 | awk '{print $3}')
  dec=$(grep -o '"decode_seconds_per_token" : [0-9.e-]*' "$OUT/score-$i.json" | tail -1 | awk '{print $3}')
  warm=$(grep -o 'decode seed prefill complete seconds=[0-9.]*' "$log" | tail -1 | sed 's/.*seconds=//')
  printf '%s\t%s\t%s\t%s\t%s\n' "$i" "$rc" "${cold:-NA}" "${warm:-NA}" "${dec:-NA}" | tee -a "$SUMMARY"
done
git checkout -- Package.resolved 2>/dev/null
cat "$SUMMARY"
