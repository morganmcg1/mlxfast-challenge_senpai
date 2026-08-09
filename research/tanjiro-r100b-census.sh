#!/usr/bin/env bash
# r100-B Part 3 primary instrument: matched same-session per-kernel counter
# census for the re-ported r85-C float4 merge epilogue.
#
# The r85-C driver's built-in BASE_SHA is the stale r85 base; this arm must be
# anchored on the r100-B assignment base instead.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

export OUT="${OUT:-/tmp/tanjiro-r100b-census}"
export SNAP="${SNAP:-/tmp/tanjiro-r100b-snap}"
export REPS="${REPS:-4}"
export STEPS="${STEPS:-200}"
export ORDER="${ORDER:-base cand cand base}"
export BASE_SHA="${BASE_SHA:-2aa2f79228d59a3eeba3abc05ec96daa9e0b99a1}"

echo "### r100-B census: BASE_SHA=${BASE_SHA} HEAD=$(git rev-parse HEAD)"
bash research/maple_r85c_epilogue_ab.sh
echo "CENSUS_EXIT=$?"
