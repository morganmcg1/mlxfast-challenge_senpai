#!/usr/bin/env bash
# Research-only (PR #629, R107-A): build the scored worker product and copy it
# into a named snapshot directory for research/maple-frieren-r103a-abba.sh.
#
#   SNAP=/tmp/maple-r107a-snap NAME=new bash research/maple-edward-r107a-build.sh
set -uo pipefail

SNAP="${SNAP:-/tmp/maple-r107a-snap}"
NAME="${NAME:-new}"

mkdir -p .build-worker/clang-module-cache "${SNAP}/${NAME}"
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker || exit 1

# The worker resolves mlx.metallib through @loader_path, so a snapshot that
# carries only the executable dies before writing its hello line.
cp .build-worker/release/mlxfast-runtime-worker "${SNAP}/${NAME}/" || exit 1
cp .build-worker/release/mlx.metallib "${SNAP}/${NAME}/" || exit 1
git rev-parse HEAD >"${SNAP}/${NAME}/head.txt"
git diff --stat -- Sources Vendor >"${SNAP}/${NAME}/tree.diffstat"
shasum -a 256 "${SNAP}/${NAME}/mlxfast-runtime-worker"
