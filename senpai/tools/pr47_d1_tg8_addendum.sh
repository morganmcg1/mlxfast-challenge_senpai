#!/bin/bash
# PR #47 D1 addendum: the tg=8 discriminator.
#
# WHY THIS EXISTS. The tg=160 ladder (pr47_d1_chain_ladder.sh) returned a
# chained/unchained slope ratio of ~1.03, not the standalone probe's 2.729.
# Two mutually exclusive explanations survive rep 1, and they imply opposite
# decisions about whether to spend a ranked M5 slot on D5:
#
#   H_host   Above the M4 knee the exposed marginal cost is CPU-side command
#            encode, which is chain-blind: a `memoryBarrier` costs the encoder
#            nothing. The ladder is then STRUCTURALLY INCAPABLE of measuring the
#            ratio -- below the knee both arms hide inside the 3.152 ms slack,
#            above it both are host-bound. D5 is still worth its slot because
#            only the M5 can answer the question.
#   H_alias  The unchained arm is still receiving barriers (MLX detects RAW/WAR/
#            WAW against recycled buffers; see research/tanjiro-pr47-d1.md).
#            The instrument is broken, and D5 would measure the instrument.
#
# THE DISCRIMINATOR. Host encode cost per dispatch is independent of grid size;
# GPU cost is not. Dropping tg 160 -> 8 (40960 -> 2048 threads/dispatch) leaves
# H_host's prediction unchanged and collapses H_alias's by ~2-7x:
#
#   arm/n            H_host (c=2.83/2.76, knee 1241/1302)   H_probe (c=1.258/0.402)
#   chained  n=3200            5.55 ms                            0.88 ms
#   chained  n=6400           14.60 ms                            4.90 ms
#   unchain  n=3200            5.24 ms                            0.00 ms
#   unchain  n=6400           14.07 ms                            0.00 ms
#
# A factor 6.3 on the chained arm at n=3200 and a zero-vs-5.24 ms split on the
# unchained arm. Run-to-run scatter on T is ~0.1-0.3 ms, so one rep decides it.
#
# tg=8 is also exactly the geometry receipt 0411779d was measured at (commit
# b8da628), so this doubles as an M4 dry run of the D5 configuration.
#
# Timing is M4 wall clock and remains INADMISSIBLE as an M5 magnitude under the
# M4 TRANSFER LAW. This script decides only whether the M4 instrument can see
# the chain at all.

set -u
cd "$(dirname "$0")/../.." || exit 1
OUT=research/tanjiro-pr47
mkdir -p "${OUT}"
TG=8
REPS="${REPS:-1}"

run_point() {
  local tag="$1" n="$2" chain="$3"
  local dest="${OUT}/d1-tg8-${tag}.json"
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

# n=0 is arm-independent and anchors the offset. The tg=160 ladder already
# measured it, but re-measuring under this process/thermal state keeps the
# addendum self-contained.
one_rep() {
  local rep="$1"
  run_point "r${rep}-n0"        0    1
  run_point "r${rep}-n3200-c1"  3200 1
  run_point "r${rep}-n3200-c0"  3200 0
  run_point "r${rep}-n6400-c0"  6400 0
  run_point "r${rep}-n6400-c1"  6400 1
}

for rep in $(seq 1 "${REPS}"); do
  one_rep "${rep}"
done

echo "=== $(date -u +%FT%TZ) tg=8 addendum complete"
ls -l "${OUT}"/d1-tg8-*.json
