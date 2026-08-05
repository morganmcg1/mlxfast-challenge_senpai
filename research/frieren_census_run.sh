#!/bin/bash
# Research-only driver for the DARKBLOOM_SCALE_CENSUS init-time scale-plane
# census (PR #35 r3 step 1). Rebuilds the participant worker into its own
# .build-worker scratch root exactly as setup.sh does (a bare
# `swift build -c release` writes .build/ and leaves the worker stale), loads
# the model once, prints the census to the worker stderr, runs two decode
# steps, exits. Not part of the submission.
set -u
cd "$(dirname "$0")/.."
OUT="${1:-/tmp/frieren_c_census.err}"

mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${CLANG_MODULE_CACHE_PATH:-${PWD}/.build-worker/clang-module-cache}" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker || exit 1
git checkout -- Package.resolved 2>/dev/null || true

export DARKBLOOM_SCALE_CENSUS=1
export DARKBLOOM_ATTN_SCALE_LANEMAJOR=0
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
python3 research/decode_probe.py --steps 2 --stderr "$OUT"
status=$?
echo "census stderr -> $OUT"
grep -c "scale-census" "$OUT" || true
exit $status
