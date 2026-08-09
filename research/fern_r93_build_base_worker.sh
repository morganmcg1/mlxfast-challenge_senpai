#!/usr/bin/env bash
# R93-B: stage an unmodified-base worker binary next to the patched one.
#
# Builds `LagunaRuntimeModel.swift` as it stands at the assignment base into
# $DEST_DIR, then restores the instrumented file and rebuilds, so
# `.build-worker/release/mlxfast-runtime-worker` is the patched binary again
# and the worktree is left exactly as it was found.
#
# The worker resolves mlx.metallib and its resource bundles from the directory
# holding the executable, so the staged copy needs those alongside it or it
# dies before writing its hello line.
set -uo pipefail
cd "$(dirname "$0")/.."
BASE_SHA="${BASE_SHA:-0fe89af7a3efd2aa744dc6774522503b090a1dbc}"
DEST_DIR="${DEST_DIR:-/tmp/r93/base}"
DEST="$DEST_DIR/mlxfast-runtime-worker"
SRC=Sources/MLXFastModel/LagunaRuntimeModel.swift
RESOURCES="mlx.metallib mlx.metallib.fingerprint mlx-swift-lm_MLXLMCommon.bundle swift-crypto_Crypto.bundle swift-transformers_Hub.bundle"

build() {
  mkdir -p .build/clang-module-cache .build-worker/clang-module-cache
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
}

mkdir -p "$DEST_DIR"
git checkout "$BASE_SHA" -- "$SRC" || exit 1
build || { git checkout HEAD -- "$SRC"; exit 1; }
cp .build-worker/release/mlxfast-runtime-worker "$DEST"
for f in $RESOURCES; do
  ln -sfn "${PWD}/.build-worker/release/$f" "$DEST_DIR/$f"
done
git checkout HEAD -- "$SRC"
build || exit 1
git checkout -- Package.resolved 2>/dev/null || true
echo "base worker  -> $DEST"
echo "patched worker -> .build-worker/release/mlxfast-runtime-worker"
git status --porcelain
