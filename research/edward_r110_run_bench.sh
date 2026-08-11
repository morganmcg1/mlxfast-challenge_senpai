#!/usr/bin/env bash
# Build + run the R110-B gather-GEMM K-loop timing rig.
# Research-only; not on editablePaths.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
BIN="${BIN:-/tmp/edr110}"
xcrun swiftc -O research/edward_r110_gemm_db_bench.swift -o "${BIN}" 2>&1 | grep -E "error:" && exit 1
exec "${BIN}"
