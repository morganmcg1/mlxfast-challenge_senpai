#!/bin/bash
# Run the vendored-Laguna upstream-equivalence oracle against the runtime.
# Zero tolerance: MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR defaults to "0".
cd "$(dirname "$0")/.." || exit 1
export MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE=1
export MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH="${PWD}/weights"

# The oracle test is a free swift-testing @Test function, not a member of a
# suite, so the filter must be the bare function name.
swift test --force-resolved-versions --no-parallel \
    --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled
status=$?

# The debug test bundle has no colocated mlx.metallib, so MLX aborts at first
# GPU use. Seed it from the worker build (Vendor/ is unchanged, so the AOT
# metallib is identical) and retry once.
if [ "${status}" -ne 0 ]; then
    src=".build-worker/arm64-apple-macosx/release/mlx.metallib"
    bundle=".build/arm64-apple-macosx/debug/mlxfast-challenge-devPackageTests.xctest/Contents/MacOS"
    if [ -f "${src}" ]; then
        cp "${src}" ".build/arm64-apple-macosx/debug/mlx.metallib"
        [ -d "${bundle}" ] && cp "${src}" "${bundle}/mlx.metallib"
        swift test --force-resolved-versions --no-parallel \
            --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled
        status=$?
    fi
fi
git checkout -- Package.resolved 2>/dev/null
echo "EQUIVALENCE_EXIT=${status}"
exit "${status}"
