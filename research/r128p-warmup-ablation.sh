#!/bin/bash
# r128-P attribution support: measure what the constructor-time warmup in
# LagunaRuntimeWeights.swift is worth to the timed prefill, by disabling it
# through the temporary DARKBLOOM_R128P_SKIP_WARMUP gate. With the warmup off
# the timed prefill becomes the genuinely first forward of the worker process,
# so the contrast against the warm-on arm is the first-use (Metal PSO creation,
# kernel JIT, first-touch page-in) cost the warmup keeps out of scored windows.
# DARKBLOOM_ is the only participant-visible prefix the runtime worker's strict
# environment allowlist forwards to the child process
# (Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:2008-2015).
# Research-only; the source gate is reverted before the result commit.
set -u
N="${1:-5}"
OUT="research/artifacts/r128p"
mkdir -p "$OUT"
SUMMARY="$OUT/nowarm.tsv"
export DARKBLOOM_R128P_SKIP_WARMUP=1
printf 'run\trc\tcold_s_per_tok\twarm_seed_seconds\tdecode_s_per_tok\n' >"$SUMMARY"
for i in $(seq 1 "$N"); do
  log="$OUT/nowarm-$i.log"
  ./benchmark.sh --local-iterate >"$log" 2>&1
  rc=$?
  cp -f score.local-iterate.json "$OUT/nowarm-score-$i.json" 2>/dev/null
  cold=$(grep -o '"prefill_seconds_per_token" : [0-9.e-]*' "$OUT/nowarm-score-$i.json" | tail -1 | awk '{print $3}')
  dec=$(grep -o '"decode_seconds_per_token" : [0-9.e-]*' "$OUT/nowarm-score-$i.json" | tail -1 | awk '{print $3}')
  warm=$(grep -o 'decode seed prefill complete seconds=[0-9.]*' "$log" | tail -1 | sed 's/.*seconds=//')
  printf '%s\t%s\t%s\t%s\t%s\n' "$i" "$rc" "${cold:-NA}" "${warm:-NA}" "${dec:-NA}" | tee -a "$SUMMARY"
done
git checkout -- Package.resolved 2>/dev/null
cat "$SUMMARY"
