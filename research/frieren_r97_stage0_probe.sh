#!/usr/bin/env bash
# r97-d Stage 0: calibrate the prefill-only work injector and run the two
# terminal gates before spending any --local-iterate time.
#
# Reads, per rung n of DARKBLOOM_INJECT_PREFILL_MATMULS:
#   * standalone 512-token prefill wall time  -> per-matmul cost delta
#   * decode_begin seed-forward wall time (S)  -> the term rule 58 claims is
#     charged to decode
#   * per-step decode times (T)                -> GATE 0a: injection must be
#     invisible to single-token steps
#   * teacher-forced divergences + token hash  -> GATE 0b: output-neutral
#
# Every arm runs the SAME binary; only the env knob differs.
set -uo pipefail
cd "$(dirname "$0")/.."

OUT="${OUT:-research/r97-runs/stage0}"
mkdir -p "$OUT"
STEPS="${STEPS:-128}"
ORDER="${ORDER:-0 32 8 0 32 8}"

i=0
for n in $ORDER; do
  i=$((i + 1))
  tag=$(printf "%02d_n%s" "$i" "$n")
  echo "=== stage0 run $tag (DARKBLOOM_INJECT_PREFILL_MATMULS=$n) $(date -u +%H:%M:%S) ==="
  DARKBLOOM_INJECT_PREFILL_MATMULS="$n" \
  MLXFAST_WEIGHTS_PATH=weights \
    python3 research/decode_probe.py \
      --steps "$STEPS" \
      --prefill \
      --stderr "$OUT/$tag.worker.err" \
      --dump-steps "$OUT/$tag.steps" \
      --dump-tokens "$OUT/$tag.tokens" \
      >"$OUT/$tag.log" 2>&1
  rc=$?
  echo "rc=$rc"
  grep -E "prefill 512 tokens|decode_begin seed forward|divergences|^decode steps=" \
    "$OUT/$tag.log" || tail -5 "$OUT/$tag.log"
  if [ "$rc" -ne 0 ]; then
    echo "ABORT: run $tag failed"
    exit "$rc"
  fi
  shasum -a 256 "$OUT/$tag.tokens" | awk '{print "tokens_sha256="$1}'
done
echo "=== stage0 complete $(date -u +%H:%M:%S) ==="
