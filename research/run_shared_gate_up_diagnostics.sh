#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
export MLXFAST_RUN_SHARED_GATE_UP_DIAGNOSTICS=1
export MLXFAST_LAGUNA_EQUIVALENCE_WEIGHTS_PATH="${PWD}/weights"

mode="${1:-}"
case "${mode}" in
    trace-control)
        export DARKBLOOM_FUSED_SHARED_GATE_UP=0
        export DARKBLOOM_SHARED_GATE_UP_TRACE=1
        filter=sharedGateUpVirtualHalfSplitKTrace
        expected='SHARED_GATE_UP_QMM M=512 N=512 K=2048 physical_n_tiles=16 selector_n_tiles=16 split_k=2 selector_engaged=0'
        expected_count=78
        ;;
    trace-candidate)
        export DARKBLOOM_FUSED_SHARED_GATE_UP=1
        export DARKBLOOM_SHARED_GATE_UP_TRACE=1
        filter=sharedGateUpVirtualHalfSplitKTrace
        expected='SHARED_GATE_UP_QMM M=512 N=1024 K=2048 physical_n_tiles=32 selector_n_tiles=16 split_k=2 selector_engaged=1'
        expected_count=39
        ;;
    exactness-timing)
        export DARKBLOOM_FUSED_SHARED_GATE_UP=1
        export DARKBLOOM_SHARED_GATE_UP_TRACE=0
        filter=sharedGateUpVirtualHalfExactnessAndTiming
        ;;
    *)
        echo "usage: $0 {trace-control|trace-candidate|exactness-timing}" >&2
        exit 2
        ;;
esac

log="$(mktemp -t mlxfast-shared-gate-up)"
trap 'rm -f "${log}"' EXIT
run_test() {
    swift test --force-resolved-versions --no-parallel --filter "${filter}" 2>&1 \
        | tee "${log}"
    return "${PIPESTATUS[0]}"
}

run_test
status=$?
if grep -q "Failed to load the default metallib" "${log}"; then
    src=".build-worker/arm64-apple-macosx/release/mlx.metallib"
    bundle=".build/arm64-apple-macosx/debug/mlxfast-challenge-devPackageTests.xctest/Contents/MacOS"
    if [ -f "${src}" ]; then
        cp "${src}" ".build/arm64-apple-macosx/debug/mlx.metallib"
        [ -d "${bundle}" ] && cp "${src}" "${bundle}/mlx.metallib"
        run_test
        status=$?
    else
        echo "diagnostics: missing ${src}; run ./benchmark.sh --local-iterate first" >&2
        status=3
    fi
fi

if [[ "${mode}" == trace-* ]]; then
    count="$(grep -c '^SHARED_GATE_UP_QMM ' "${log}" || true)"
    bad="$(awk -v expected="${expected}" '/^SHARED_GATE_UP_QMM / { if ($0 != expected) n++ } END { print n + 0 }' "${log}")"
    decode_count="$(awk '/GATE0_DECODE_BEGIN/ { active=1; next } /GATE0_DECODE_END/ { active=0 } active && /^SHARED_GATE_UP_QMM / { n++ } END { print n + 0 }' "${log}")"
    decode_engaged="$(awk '/GATE0_DECODE_BEGIN/ { active=1; next } /GATE0_DECODE_END/ { active=0 } active && /selector_engaged=1/ { n++ } END { print n + 0 }' "${log}")"
    echo "GATE0_TRACE mode=${mode} count=${count} expected=${expected_count} bad=${bad} decode_count=${decode_count} decode_engaged=${decode_engaged}"
    if [ "${count}" -ne "${expected_count}" ] || [ "${bad}" -ne 0 ] || [ "${decode_engaged}" -ne 0 ]; then
        status=4
    fi
    grep -q 'GATE0_REPORT' "${log}" || status=5
else
    grep -q 'GATE1_REPORT' "${log}" || status=5
    grep -q 'GATE2_REPORT' "${log}" || status=5
fi

echo "SHARED_GATE_UP_DIAGNOSTICS_EXIT=${status}"
exit "${status}"
