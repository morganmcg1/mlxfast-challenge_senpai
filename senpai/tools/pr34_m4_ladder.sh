#!/bin/bash
# PR #34 r2: local M4 companion ladder for the M5 dispatch-saturation law.
#
# Runs ./benchmark.sh --local-iterate once per (empty-dispatch count, threadgroup)
# pair and archives each score file. The injection knobs are read from the
# environment through lagunaInjectEnvInt, so no rebuild is needed between points;
# the official receipts must edit the default literals instead.
#
# The anchor (0, 8) runs first and last as a drift control. The tg triple at
# n=2400 measures the injected dispatch's own GPU time, which the ladder needs to
# be negligible.

set -u
cd "$(dirname "$0")/../.." || exit 1
OUT=research/tanjiro-pr34
mkdir -p "${OUT}"

run_point() {
  local tag="$1" n="$2" tg="$3"
  local dest="${OUT}/m4r2-${tag}.json"
  echo "=== $(date -u +%FT%TZ) point ${tag}: DECODE_EMPTY=${n} EMPTY_TG=${tg}"
  rm -f score.local-iterate.json
  DARKBLOOM_INJECT_DECODE_EMPTY="${n}" \
  DARKBLOOM_INJECT_PREFILL_EMPTY=0 \
  DARKBLOOM_INJECT_EMPTY_TG="${tg}" \
    ./benchmark.sh --local-iterate
  local rc=$?
  if [[ -f score.local-iterate.json ]]; then
    cp score.local-iterate.json "${dest}"
    echo "=== $(date -u +%FT%TZ) point ${tag} rc=${rc} -> ${dest}"
  else
    echo "=== $(date -u +%FT%TZ) point ${tag} rc=${rc} PRODUCED NO SCORE FILE"
  fi
  git checkout -- Package.resolved 2>/dev/null
}

run_point n0-tg8-a      0    8
run_point n400-tg8    400    8
run_point n800-tg8    800    8
run_point n1600-tg8  1600    8
run_point n2400-tg8  2400    8
run_point n2400-tg160 2400 160
run_point n2400-tg512 2400 512
run_point n0-tg8-b      0    8

echo "=== $(date -u +%FT%TZ) ladder complete"
ls -l "${OUT}"/m4r2-*.json
