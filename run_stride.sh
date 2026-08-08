#!/bin/bash
set -euo pipefail

STRIDE="${1:?usage: run_stride.sh <stride> [suffix]}"
SUFFIX="${2:-stride${STRIDE}}"
SCORE_PATH="score.local-iterate.${SUFFIX}.json"

echo "run_stride.sh: stride=${STRIDE} suffix=${SUFFIX} score_path=${SCORE_PATH}"

if [ "$STRIDE" = "0-off" ] || [ "$STRIDE" = "off" ]; then
  export DARKBLOOM_PREFILL_ASYNC_LADDER="0"
else
  export DARKBLOOM_PREFILL_ASYNC_LADDER="$STRIDE"
fi

export MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1

./benchmark.sh --local-iterate

# Copy the score to our named file
if [ -f score.local-iterate.json ]; then
  cp score.local-iterate.json "$SCORE_PATH"
  echo "run_stride.sh: copied score to ${SCORE_PATH}"
else
  echo "run_stride.sh: WARNING score.local-iterate.json not found"
fi
