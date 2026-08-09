#!/usr/bin/env bash
# R93-B: build the runtime worker into the same scratch path benchmark.sh uses.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p .build/clang-module-cache .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
exit $rc
