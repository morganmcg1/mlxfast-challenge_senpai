#!/bin/bash
# R108-M Part 2 — timed dry-run of the two build products benchmark.sh drives.
# Scratch paths are OUTSIDE the checkout so predicate 12 (clean -uall --ignored=matching
# over Sources/ and Vendor/) stays green while this runs.
set -u
cd "$(dirname "$0")/../../.." || exit 1
echo "repo=$(pwd)"
echo "head=$(/usr/bin/git rev-parse HEAD)"
date -u

W=/tmp/fern-freeze-worker
rm -rf "$W"
echo "=== [1] cold release build, product mlxfast-runtime-worker (benchmark.sh:2022) ==="
/usr/bin/time -p swift build -c release --force-resolved-versions \
  --scratch-path "$W" --product mlxfast-runtime-worker 2>&1 | tail -6
echo "rc=$?"
date -u

echo
echo "=== [2] incremental rebuild, product mlxfast-swift, after touching the one file"
echo "        a frieren decode-dispatch candidate would edit ==="
touch Sources/MLXFastModel/LagunaRuntimeModel.swift
/usr/bin/time -p swift build -c release --force-resolved-versions \
  --scratch-path /tmp/fern-freeze-build --product mlxfast-swift 2>&1 | tail -6
echo "rc=$?"
date -u

echo
echo "=== [3] incremental rebuild, product mlxfast-runtime-worker, same edit ==="
touch Sources/MLXFastModel/LagunaRuntimeModel.swift
/usr/bin/time -p swift build -c release --force-resolved-versions \
  --scratch-path "$W" --product mlxfast-runtime-worker 2>&1 | tail -6
echo "rc=$?"
date -u

echo
echo "=== [4] no-op rebuild (both products already current) ==="
/usr/bin/time -p swift build -c release --force-resolved-versions \
  --scratch-path /tmp/fern-freeze-build --product mlxfast-swift 2>&1 | tail -3
date -u

echo
echo "=== worktree still clean over the submitted surface? ==="
/usr/bin/git status --porcelain=v1 -uall --ignored=matching -- Sources Vendor
echo "(empty above == predicate 12 green)"
rm -rf "$W"
echo done
