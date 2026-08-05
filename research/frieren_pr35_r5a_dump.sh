#!/bin/bash
# Research-only driver for the PR #35 r5-A artifact dump. Not part of the submission.
#
# Reproduce with:
#   git apply research/frieren-pr35-r5a-dump.patch
#   CLANG_MODULE_CACHE_PATH=$PWD/.build-worker/clang-module-cache \
#     swift build -c release --force-resolved-versions --scratch-path .build-worker \
#     --product mlxfast-runtime-worker
#   git checkout -- Package.resolved Sources/      # instrument then lives only in the binary
#   bash research/frieren_pr35_r5a_dump.sh
#
# The patch adds two temporary instruments:
#   * LagunaRuntimeWeights.swift writes the real fused-QKV scale plane plus the
#     derived lane-major nibbles/bases for every layer to $DARKBLOOM_DUMP_PLANE_DIR;
#   * LagunaRuntimeModel.swift re-applies both decode QKV kernels with MLX's
#     `verbose: true` and captures fd 1 into $DARKBLOOM_DUMP_GEN_DIR/gen_h<H>.txt
#     (the worker's stdout is the JSON protocol channel, so it must be redirected).
# The dumped generated Metal sources are what research/frieren_pr35_lanemajor_bitwise.swift
# compiles, so the standalone oracle never has to re-derive MLX's write_signature.
set -u
cd "$(dirname "$0")/.."
DIR="${1:-/tmp/pr35_r5a}"
OUT="${2:-/tmp/pr35_r5a_dump.err}"
WORKER=.build-worker/release/mlxfast-runtime-worker
if [ ! -x "$WORKER" ]; then
  echo "missing $WORKER; build it from research/frieren-pr35-r5a-dump.patch first" >&2
  exit 1
fi
mkdir -p "$DIR"

export DARKBLOOM_DUMP_PLANE_DIR="$DIR"
export DARKBLOOM_DUMP_GEN_DIR="$DIR"
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
python3 research/decode_probe.py --steps 2 --stderr "$OUT"
status=$?
echo "dump dir -> $DIR"
grep -c "dump-plane" "$OUT" || true
ls "$DIR" | wc -l
du -sh "$DIR"
exit $status
