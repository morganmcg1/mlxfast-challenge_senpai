#!/bin/bash
# Run the vendored-Laguna upstream-equivalence oracle against the runtime.
# Zero tolerance: MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR defaults to "0".
cd "$(dirname "$0")/.." || exit 1
export MLXFAST_RUN_LAGUNA_UPSTREAM_EQUIVALENCE=1
export MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH="${PWD}/weights"
swift test --force-resolved-versions \
    --filter LagunaCorrectnessTests.lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled
status=$?
git checkout -- Package.resolved 2>/dev/null
echo "EQUIVALENCE_EXIT=${status}"
exit "${status}"
