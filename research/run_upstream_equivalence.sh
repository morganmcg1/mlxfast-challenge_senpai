#!/bin/bash
# Run the vendored-Laguna upstream-equivalence oracle against the runtime.
# Zero tolerance: MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR defaults to "0".
cd "$(dirname "$0")/.." || exit 1
export MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE=1
export MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH="${PWD}/weights"

log="$(mktemp -t mlxfast-equivalence)"

run_oracle() {
    # The oracle is a free swift-testing @Test function with no enclosing
    # suite, so the filter must be the bare function name. A qualified name
    # selects zero tests and still exits 0.
    swift test --force-resolved-versions --no-parallel \
        --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled 2>&1 \
        | tee -a "${log}"
    return "${PIPESTATUS[0]}"
}

run_oracle
status=$?

# The debug test bundle has no colocated mlx.metallib and MLX offers no
# environment override, so it aborts at first GPU use. Seed the metallib from
# the worker build (Vendor/ is unchanged, so the AOT library is identical).
if grep -q "Failed to load the default metallib" "${log}"; then
    src=".build-worker/arm64-apple-macosx/release/mlx.metallib"
    bundle=".build/arm64-apple-macosx/debug/mlxfast-challenge-devPackageTests.xctest/Contents/MacOS"
    if [ -f "${src}" ]; then
        cp "${src}" ".build/arm64-apple-macosx/debug/mlx.metallib"
        [ -d "${bundle}" ] && cp "${src}" "${bundle}/mlx.metallib"
        run_oracle
        status=$?
    fi
fi

# The default tolerance of 0 is applied to every step including prefill, which
# the batched NVFP4 path cannot meet against the bf16 upstream reference. Read
# the per-step table above rather than this exit code.
grep -c '"maximumAbsoluteLogitError" : 0,' "${log}" \
    | sed 's/^/EQUIVALENCE_EXACT_STEPS=/'
git checkout -- Package.resolved 2>/dev/null
echo "EQUIVALENCE_EXIT=${status}"
exit "${status}"
