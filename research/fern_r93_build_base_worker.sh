#!/usr/bin/env bash
# R93-B: stage an unmodified-base worker binary next to the patched one.
#
# Builds `LagunaRuntimeModel.swift` as it stands at the assignment base into
# /tmp/r93/worker-base, then restores the instrumented file and rebuilds, so
# `.build-worker/release/mlxfast-runtime-worker` is the patched binary again
# and the worktree is left exactly as it was found.
set -uo pipefail
cd "$(dirname "$0")/.."
BASE_SHA="${BASE_SHA:-0fe89af7a3efd2aa744dc6774522503b090a1dbc}"
DEST="${DEST:-/tmp/r93/worker-base}"
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift

build() {
  mkdir -p .build/clang-module-cache .build-worker/clang-module-cache
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
}

mkdir -p "$(dirname "$DEST")"
git checkout "$BASE_SHA" -- "$SRC" || exit 1
build || { git checkout HEAD -- "$SRC"; exit 1; }
cp .build-worker/release/mlxfast-runtime-worker "$DEST"
git checkout HEAD -- "$SRC"
build || exit 1
git checkout -- Package.resolved 2>/dev/null || true
echo "base worker  -> $DEST"
echo "patched worker -> .build-worker/release/mlxfast-runtime-worker"
git status --porcelain
