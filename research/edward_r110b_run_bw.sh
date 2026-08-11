#!/usr/bin/env bash
# Build + run the R110-B Stage-0 streaming-read ceiling probe. Research-only.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
BIN="${BIN:-/tmp/edbw}"
xcrun swiftc -O research/edward_r110b_bw_bench.swift -o "${BIN}" 2>&1 | grep -E "error:" && exit 1
exec "${BIN}"
