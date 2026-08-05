#!/bin/bash
# Run the vendored-Laguna upstream-equivalence oracle against the runtime.
# Zero tolerance: MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR defaults to "0".
cd "$(dirname "$0")/.." || exit 1
export MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE=1
export MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH="${PWD}/weights"

log="$(mktemp -t mlxfast-equivalence)"
trap 'rm -f "${log}"' EXIT

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
# the scored worker build and retry once.
if grep -q "Failed to load the default metallib" "${log}"; then
    src=".build-worker/arm64-apple-macosx/release/mlx.metallib"
    bundle=".build/arm64-apple-macosx/debug/mlxfast-challenge-devPackageTests.xctest/Contents/MacOS"
    if [ -f "${src}" ]; then
        cp "${src}" ".build/arm64-apple-macosx/debug/mlx.metallib"
        [ -d "${bundle}" ] && cp "${src}" "${bundle}/mlx.metallib"
        run_oracle
        status=$?
    else
        echo "equivalence: missing ${src}; run ./benchmark.sh --local-iterate first" >&2
    fi
fi

# A mismatched Swift Testing filter exits zero after selecting no tests. The
# report marker proves that this specific gated test reached its comparison.
if ! grep -q '"promptTokenCount"' "${log}"; then
    echo "equivalence: oracle report missing; zero selected tests is not a pass" >&2
    status=3
fi

# Zero tolerance covers prefill as well as decode. Read the per-step report;
# on a non-M5 host, compare the unchanged BASE_SHA before attributing drift.
grep -c '"maximumAbsoluteLogitError" : 0,' "${log}" \
    | sed 's/^/EQUIVALENCE_EXACT_STEPS=/'
echo "EQUIVALENCE_EXIT=${status}"
exit "${status}"
