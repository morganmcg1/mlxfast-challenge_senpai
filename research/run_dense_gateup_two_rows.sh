#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

case "${1:-}" in
oracle)
    export MLXFAST_RUN_DENSE_GATEUP_ORACLE=1
    swift test -c release --force-resolved-versions --no-parallel \
        --filter denseGateUpTwoRowsMatchesFourRowsBitwiseWhenEnabled
    ;;
isolated-ab|isolated-ba)
    ./benchmark.sh --local-cool-gate-only || exit $?
    export MLXFAST_RUN_DENSE_GATEUP_ISOLATED=1
    if [ "$1" = "isolated-ab" ]; then
        export MLXFAST_DENSE_GATEUP_TIMING_ORDER=AB
    else
        export MLXFAST_DENSE_GATEUP_TIMING_ORDER=BA
    fi
    swift test -c release --force-resolved-versions --no-parallel \
        --filter denseGateUpTwoRowsIsolatedTimingWhenEnabled
    ;;
*)
    echo "usage: $0 {oracle|isolated-ab|isolated-ba}" >&2
    exit 2
    ;;
esac
