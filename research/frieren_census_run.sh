#!/bin/bash
# Research-only driver for the DARKBLOOM_SCALE_CENSUS init-time scale-plane
# census (PR #35 r3 step 1). Loads the model once, prints the census to the
# worker stderr, runs two decode steps, exits. Not part of the submission.
set -u
cd "$(dirname "$0")/.."
export DARKBLOOM_SCALE_CENSUS=1
export DARKBLOOM_ATTN_SCALE_LANEMAJOR=0
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
OUT="${1:-/tmp/frieren_c_census.err}"
python3 research/decode_probe.py --steps 2 --stderr "$OUT"
status=$?
echo "census stderr -> $OUT"
grep -c "scale-census" "$OUT" || true
exit $status
