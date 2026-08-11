#!/usr/bin/env bash
# R117-C Stage 1: the o_proj geometry ladder.
# Pre-registered in research/nezuko-r117-oproj-geometry-preregistration.md
# amendment 11, committed BEFORE this script ever ran.
#
#   5 arms x 5 blocks = 25 runs ~= 65 min.
#
# Arms (rps = DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP, ns = DARKBLOOM_OPROJ_SIMDGROUPS):
#
#   arm  rps ns  simdgroups  threadgroups  act MB/step   d(act)
#   C     4  2     512          256          314.57         0     <- shipped default
#   R1    1  2    2048         1024         1258.29   +943.72
#   R2    2  2    1024          512          629.15   +314.57
#   R8    8  2     256          128          157.29   -157.29
#   N4    4  4     512          128          314.57         0     <- zero-dose control
#
# The design is a 2x2 tease, not a one-dimensional dose ladder:
#   * simdgroup count (== activation re-read traffic): C 512, R1 2048, R2 1024, R8 256, N4 512
#   * threadgroup count (== dispatch parallelism):     C 256, R1 1024, R2  512, R8 128, N4 128
#   N4 vs C  : same simdgroups, HALF the threadgroups -> isolates threadgroup granularity
#   R8 vs N4 : same threadgroups, HALF the simdgroups -> isolates simdgroups/bytes
# So N4 is analysed as a separate paired contrast, NEVER as a regression rung.
#
# Do not stop this early. The block count is pre-registered.
set -u
cd "$(dirname "$0")/../.."
OUT="${OUT:-/tmp/r117-stage1-ladder-$(date -u +%Y%m%dT%H%M%SZ).tsv}"
export OUT
echo "R117-C Stage 1 ladder starting $(date -u) -> $OUT"
exec research/maple-nezuko-r107j-certify.sh --blocks 5 \
  C: \
  R1:DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=1 \
  R2:DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=2 \
  R8:DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=8 \
  N4:DARKBLOOM_OPROJ_SIMDGROUPS=4
