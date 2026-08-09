#!/bin/bash
# Run the upstream-equivalence oracle against the UNCHANGED base source, so a
# non-zero prefill logit error on this non-M5 host can be attributed to the
# host rather than to the r100-B epilogue port. Always restores HEAD.
set -u
cd "$(dirname "$0")/.." || exit 1
BASE_SHA="${BASE_SHA:-2aa2f79228d59a3eeba3abc05ec96daa9e0b99a1}"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"

if [ -n "$(git status --porcelain -- "${SRC}")" ]; then
    echo "refusing: ${SRC} is dirty" >&2
    exit 2
fi

restore() {
    git checkout HEAD -- "${SRC}"
    git checkout -- Package.resolved 2>/dev/null
    echo "restored ${SRC} to HEAD ($(git rev-parse --short HEAD))"
}
trap restore EXIT

echo "=== base ${BASE_SHA} ==="
git checkout "${BASE_SHA}" -- "${SRC}" || exit 3
md5 -q "${SRC}"
bash research/run_upstream_equivalence.sh
echo "BASE_RUN_EXIT=$?"
