#!/bin/bash
# R109-D stage 0b driver: paired A/B timing of the sliding kernel QK reduction.
#
#   bash research/edward-r109/run_probe.sh ARM [DEFEAT_SLOTS]
#
# ARM = "null" runs base against itself (instrument bias floor); any other value
# names a research/edward-r109/cand_ARM.swift arm. The ladder is pinned to the
# scored geometry (32 threadgroups = 64 query heads / 2) because this round is
# forbidden from changing threadgroup shape.
set -u
cd "$(dirname "$0")/../.." || exit 1

ARM="${1:?usage: run_probe.sh ARM [DEFEAT_SLOTS] [TAG]}"
SLOTS="${2:-64}"
TAG="${3:-}"
BASE="Sources/MLXFastModel/LagunaRuntimeModel.swift"
OUT="research/edward-r109/probe_${ARM}${TAG}_slots${SLOTS}.txt"

if [ ! -x /tmp/fernattn ]; then
  xcrun swiftc -O research/fern_r100_attn_probe.swift -o /tmp/fernattn || exit 1
fi

ARGS=("$BASE")
if [ "$ARM" != "null" ]; then
  ARGS+=("research/edward-r109/cand_${ARM}.swift")
fi

# 64 defeat slots stride 1 MiB each, so 6 logical cache copies keep the rotation
# in bounds with headroom.
export FERN_LADDER=32
export FERN_ROUNDS="${FERN_ROUNDS:-21}"
export FERN_REPS="${FERN_REPS:-200}"
export FERN_DEFEAT_SLOTS="$SLOTS"
export FERN_CACHE_COPIES="${FERN_CACHE_COPIES:-6}"

echo "arm=$ARM slots=$SLOTS rounds=$FERN_ROUNDS reps=$FERN_REPS" | tee "$OUT"
/tmp/fernattn "${ARGS[@]}" 2>&1 | tee -a "$OUT"
