#!/usr/bin/env bash
# R106-F': build the *pinned ranked-baseline* runtime worker.
#
# The ranked denominator is not the vendored Laguna.swift oracle: it is commit
# 15852ee5 ("Pin Poolside v2 private benchmark artifacts", #756), installed as
# the signed baseline workspace on M5-A and run as a full `./benchmark.sh
# --official` in its own fresh worker process
# (.github/workflows/benchmark.yml:139-147, docs/benchmark-window-freeze.md:176-190).
# That commit is an ancestor of this branch, so the paired baseline tree can be
# built and timed locally for the first time in this campaign.
#
# Both trees get the identical GPUPROF hook so instrument overhead is
# common-mode in every ratio. The worker resolves mlx.metallib and its resource
# bundles from the directory holding the executable, so the staged copy needs
# those alongside it.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
BASE_COMMIT="${BASE_COMMIT:-15852ee52858def42ddd4f32bca7e59d275e020e}"
WT="${WT:-/tmp/r106f-base}"
DEST_DIR="${DEST_DIR:-/tmp/r106f/base}"
PATCH="$REPO/research/pr91-gpuprof-hook.patch"
HOOK=Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp
RESOURCES="mlx.metallib mlx.metallib.fingerprint mlx-swift-lm_MLXLMCommon.bundle swift-crypto_Crypto.bundle swift-transformers_Hub.bundle"

build() {
  local dir="$1"
  ( cd "$dir" \
    && mkdir -p .build-worker/clang-module-cache \
    && CLANG_MODULE_CACHE_PATH="$dir/.build-worker/clang-module-cache" \
       swift build -c release --force-resolved-versions \
         --scratch-path .build-worker --product mlxfast-runtime-worker )
}

echo "### candidate tree: $(git -C "$REPO" rev-parse HEAD)"
grep -q GPUPROF "$REPO/$HOOK" || { echo "FATAL: candidate GPUPROF hook missing" >&2; exit 1; }
build "$REPO" || { echo "FATAL: candidate build failed" >&2; exit 1; }

if [ ! -d "$WT" ]; then
  git -C "$REPO" worktree add --detach "$WT" "$BASE_COMMIT" || exit 1
  ( cd "$WT" && git apply "$PATCH" ) || exit 1
fi
echo "### baseline tree: $(git -C "$WT" rev-parse HEAD)"
[ "$(git -C "$WT" rev-parse HEAD)" = "$BASE_COMMIT" ] || { echo "FATAL: worktree is not the pinned baseline" >&2; exit 1; }
grep -q GPUPROF "$WT/$HOOK" || { echo "FATAL: baseline GPUPROF hook missing" >&2; exit 1; }
build "$WT" || { echo "FATAL: baseline build failed" >&2; exit 1; }

mkdir -p "$DEST_DIR"
cp "$WT/.build-worker/release/mlxfast-runtime-worker" "$DEST_DIR/mlxfast-runtime-worker"
for f in $RESOURCES; do ln -sfn "$WT/.build-worker/release/$f" "$DEST_DIR/$f"; done

echo "### Rule 75 artifacts"
for p in "$REPO/.build-worker/release/mlxfast-runtime-worker" "$DEST_DIR/mlxfast-runtime-worker"; do
  echo "$(shasum -a 256 "$p" | cut -d' ' -f1)  $(stat -f '%z' "$p") bytes  $p"
done
git -C "$REPO" checkout -- Package.resolved 2>/dev/null || true
git -C "$WT" checkout -- Package.resolved 2>/dev/null || true
echo "baseline worker  -> $DEST_DIR/mlxfast-runtime-worker"
echo "candidate worker -> $REPO/.build-worker/release/mlxfast-runtime-worker"
