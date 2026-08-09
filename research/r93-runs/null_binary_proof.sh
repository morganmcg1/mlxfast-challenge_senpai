#!/bin/bash
# Prove that appending a trailing Swift comment to LagunaRuntimeModel.swift is a
# machine-code null: build the scored worker twice, once with the module forced
# to recompile from unchanged bytes and once from the comment-appended bytes,
# and compare sha256 of the emitted binary.
#
# usage: null_binary_proof.sh <marker-text>
set -u

ROOT="$(pwd)"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
BIN=".build-worker/release/mlxfast-runtime-worker"
MARKER="${1:-senpai-r93-null-probe}"
OUT="/tmp/r93"
mkdir -p "$OUT"

build() {
  mkdir -p .build-worker/clang-module-cache
  CLANG_MODULE_CACHE_PATH="${ROOT}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker \
      > "${OUT}/build-$1.log" 2>&1
  echo "build $1 rc=$?"
}

echo "start=$(date -u +%Y-%m-%dT%H:%M:%SZ) head=$(git rev-parse HEAD)"
git status --porcelain -- "$SRC"

# Control: force a full recompile of the module from byte-identical source.
touch "$SRC"
build control
H0="$(shasum -a 256 "$BIN" | cut -d' ' -f1)"
echo "control_sha256=$H0"
cp "$BIN" "${OUT}/worker-control.bin"

# Treatment: append a trailing comment (no line numbers shift, no string
# literal touched) and rebuild.
printf '\n// %s\n' "$MARKER" >> "$SRC"
tail -3 "$SRC"
build null
H1="$(shasum -a 256 "$BIN" | cut -d' ' -f1)"
echo "null_sha256=$H1"

if [ "$H0" = "$H1" ]; then
  echo "VERDICT: machine-code null CONFIRMED (identical worker binary)"
else
  echo "VERDICT: binaries DIFFER — investigating"
  cmp -l "${OUT}/worker-control.bin" "$BIN" | head -20
  cmp -l "${OUT}/worker-control.bin" "$BIN" | wc -l
fi

git checkout -- Package.resolved 2>/dev/null
echo "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
