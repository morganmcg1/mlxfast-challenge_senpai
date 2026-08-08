#!/bin/bash
# Research-only helper: build the runtime worker into .build-worker the same way
# research/decode_probe.py expects, without disturbing Package.resolved.
set -uo pipefail
cd "$(dirname "$0")/.."
export CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache"
swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
status=$?
git checkout -- Package.resolved 2>/dev/null || true
exit "$status"
