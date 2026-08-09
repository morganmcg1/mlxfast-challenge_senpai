#!/bin/bash
# Research-only: dump the compiler-resolved shared SwiGLU QMV header so the r99
# probe compiles the exact MSL the runtime ships, instead of a hand copy.
set -uo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)" || exit 1
export FERN_R99_DUMP_DIR="$PWD/research/artifacts/fern-r99"
mkdir -p "$FERN_R99_DUMP_DIR"
swift test --force-resolved-versions --filter fernR99DumpSharedQMVHeader
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
exit $rc
