#!/bin/bash
# PR #47 D1: interleaved chained-vs-unchained in-model dispatch ladder (M4).
#
# Measures the marginal cost of an injected empty decode dispatch with the RAW
# chain on (DARKBLOOM_INJECT_EMPTY_CHAIN=1, the shipped instrument) and off (=0,
# no memoryBarrier emitted), fitting slope AND offset independently per arm.
#
# Design constraints this script exists to satisfy:
#   * >=3 supra-knee points per arm. The M4 host-encode knee is 1209
#     (`research/tanjiro-pr34-*`), so n in {1600, 2400, 3200} are all supra-knee
#     and n=0 anchors the offset. n=0 is arm-independent (empties=0) and is
#     therefore measured once per rep and shared by both fits.
#   * arms interleaved within a rep, so any drift across the ladder enters both
#     arms equally instead of loading onto one.
#   * fresh process per point: every ./benchmark.sh --local-iterate is its own
#     worker process, so no JIT/allocator state carries between cells.
#   * the first point is a discarded warm-up arm.
#   * tg=160 matches both the standalone Metal probe datum and the r1 in-model
#     fit c=2.607 us, so the two instruments are comparable.
#
# Timing here is M4 wall clock. Per the M4 TRANSFER LAW (nezuko, PR #44) this is
# INADMISSIBLE as an M5 magnitude for a boundary/concurrency-class quantity. The
# chained/unchained ratio is exactly such a quantity. This ladder is therefore
# an M4-side bound and an instrument validation, not a transfer.

set -u
cd "$(dirname "$0")/../.." || exit 1
OUT=research/tanjiro-pr47
mkdir -p "${OUT}"
TG=160

run_point() {
  local tag="$1" n="$2" chain="$3"
  local dest="${OUT}/d1-${tag}.json"
  if [[ -f "${dest}" ]]; then
    echo "=== $(date -u +%FT%TZ) point ${tag}: already present, skipping"
    return 0
  fi
  echo "=== $(date -u +%FT%TZ) point ${tag}: EMPTY=${n} CHAIN=${chain} TG=${TG}"
  rm -f score.local-iterate.json
  DARKBLOOM_INJECT_DECODE_EMPTY="${n}" \
  DARKBLOOM_INJECT_PREFILL_EMPTY=0 \
  DARKBLOOM_INJECT_EMPTY_CHAIN="${chain}" \
  DARKBLOOM_INJECT_EMPTY_TG="${TG}" \
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

# Warm-up arm, discarded. Also the build/preflight fast-fail gate.
run_point warmup 2400 1
if [[ ! -f "${OUT}/d1-warmup.json" ]]; then
  echo "=== warm-up produced no score file; aborting before burning the budget"
  exit 1
fi

# Reps are ordered so that rep 1 alone is a complete 2-arm 4-point ladder; if
# the wall-clock budget truncates the run, every completed rep is still a fit.
for rep in 1 2 3; do
  run_point "r${rep}-n0"        0    1
  run_point "r${rep}-n1600-c1"  1600 1
  run_point "r${rep}-n1600-c0"  1600 0
  run_point "r${rep}-n2400-c0"  2400 0
  run_point "r${rep}-n2400-c1"  2400 1
  run_point "r${rep}-n3200-c1"  3200 1
  run_point "r${rep}-n3200-c0"  3200 0
done

echo "=== $(date -u +%FT%TZ) ladder complete"
ls -l "${OUT}"/d1-*.json
