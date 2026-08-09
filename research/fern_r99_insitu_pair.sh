#!/usr/bin/env bash
# Interleaved in-situ A/B leg for the r99-e unrolled routed gate/up qmv kernel.
#
# Section 5.3 of the rung log showed a single base->cand->base bracket cannot
# resolve this effect on M4: the identical-code control spread (-49.9 us/token)
# was larger than the candidate delta, because both drift monotonically with
# wall clock. An ABBA sequence cancels any linear drift exactly, so the paired
# contrast is unbiased under a linear trend and the residual is an honest
# spread estimate.
#
# Usage: research/fern_r99_insitu_pair.sh BASE_SHA [REPEATS]

set -uo pipefail

BASE_SHA="${1:?usage: fern_r99_insitu_pair.sh BASE_SHA [REPEATS]}"
REPEATS="${2:-2}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FILE="Sources/MLXFastModel/LagunaRuntimeModel.swift"
OUT="research/artifacts/fern-r99"
TMP="$(mktemp -d)"
mkdir -p "$OUT"

git show "${BASE_SHA}:${FILE}" > "$TMP/base.swift"
git show "HEAD:${FILE}" > "$TMP/cand.swift"
CAND_SHA="$(git rev-parse --short HEAD)"

restore() { cp "$TMP/cand.swift" "$FILE"; }
trap restore EXIT

if cmp -s "$TMP/base.swift" "$TMP/cand.swift"; then
  echo "FATAL: base and candidate ${FILE} are identical; nothing to contrast" >&2
  exit 2
fi

run_arm() {
  local arm="$1" idx="$2"
  cp "$TMP/${arm}.swift" "$FILE"
  echo "=== arm=${arm} idx=${idx} $(date -u +%H:%M:%S) md5=$(md5 -q "$FILE") ==="
  rm -f score.local-iterate.json
  if ! ./benchmark.sh --local-iterate; then
    echo "=== arm=${arm} idx=${idx} benchmark.sh FAILED ===" >&2
  fi
  if [[ -f score.local-iterate.json ]]; then
    cp score.local-iterate.json "$OUT/insitu_${arm}_${idx}.json"
    python3 -c "
import json,sys
m=json.load(open('$OUT/insitu_${arm}_${idx}.json'))['metrics']
print('    decode=%.9f prefill=%.9f pass=%s max_abs_diff=%s ts=%s' % (
    m['decode_seconds_per_token'], m['prefill_seconds_per_token'],
    m['passed_correctness'], m['max_abs_diff'], m['timestamp']))"
  else
    echo "    NO SCORE FILE" >&2
  fi
}

echo "candidate=${CAND_SHA} base=${BASE_SHA} repeats=${REPEATS} sequence=ABBA"
i=0
for ((r = 0; r < REPEATS; r++)); do
  for arm in base cand cand base; do
    i=$((i + 1))
    run_arm "$arm" "$i"
  done
done

echo "=== summary ==="
python3 research/fern_r99_insitu_summarize.py "$OUT"
