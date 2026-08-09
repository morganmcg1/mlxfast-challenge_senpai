#!/bin/bash
# Capture MLX's generated MSL for every scored-runtime custom kernel.
#
# Vehicle: the upstream-equivalence oracle. It is the only in-tree path that
# drives a real prefill + 8 decode steps with stdout intact --
# mlxfast-runtime-worker redirects STDOUT_FILENO to /dev/null
# (Sources/MLXFastHarness/LagunaRuntimeWorker.swift:1187), so MLX's std::cout
# verbose dump is unrecoverable under ./benchmark.sh.
#
# Prerequisite: senpai/tools/agx-census-probe/add_verbose_dump.py applied.
# Output: $1 (default research/r92-runs/verbose-dump.log)
cd "$(dirname "$0")/../../.." || exit 1
out="${1:-research/r92-runs/verbose-dump.log}"
mkdir -p "$(dirname "${out}")"

export MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE=1
export MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH="${PWD}/weights"

# The debug test bundle has no colocated mlx.metallib and MLX offers no
# environment override, so seed it up front from the scored worker build.
src=".build-worker/arm64-apple-macosx/release/mlx.metallib"
bundle=".build/arm64-apple-macosx/debug/mlxfast-challenge-devPackageTests.xctest/Contents/MacOS"
if [ -f "${src}" ]; then
    mkdir -p ".build/arm64-apple-macosx/debug"
    cp "${src}" ".build/arm64-apple-macosx/debug/mlx.metallib"
    [ -d "${bundle}" ] && cp "${src}" "${bundle}/mlx.metallib"
fi

# Bare function name: the oracle is a free @Test with no enclosing suite, and a
# qualified filter selects zero tests while still exiting 0.
swift test --force-resolved-versions --no-parallel \
    --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled \
    >"${out}" 2>&1
status=$?

if grep -q "Failed to load the default metallib" "${out}"; then
    if [ -f "${src}" ]; then
        [ -d "${bundle}" ] && cp "${src}" "${bundle}/mlx.metallib"
        swift test --force-resolved-versions --no-parallel \
            --filter lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled \
            >"${out}" 2>&1
        status=$?
    else
        echo "dump: missing ${src}; run ./benchmark.sh --local-iterate first" >&2
    fi
fi

git checkout -- Package.resolved 2>/dev/null

# A mismatched filter exits zero after selecting no tests. The report marker
# proves this specific gated test reached its comparison.
if ! grep -q '"promptTokenCount"' "${out}"; then
    echo "dump: oracle report missing; zero selected tests is not a pass" >&2
    status=3
fi

echo "DUMP_BYTES=$(wc -c <"${out}")"
echo "DUMP_KERNELS=$(grep -c 'Generated source code for' "${out}")"
grep -c '"maximumAbsoluteLogitError" : 0,' "${out}" \
    | sed 's/^/EQUIVALENCE_EXACT_STEPS=/'
echo "DUMP_EXIT=${status}"
exit "${status}"
