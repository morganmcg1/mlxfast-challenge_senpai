#!/bin/bash
# r99-A end-to-end paired local benchmark, alternating arm order.
#
# Sweep i runs BASE then CAND when i is odd (FWD) and CAND then BASE when i is
# even (REV). The kernel-level probe for this same change showed a ~1% bias
# favouring whichever arm occupies the second timing slot, so a single fixed
# order is not trustworthy; the estimator is (FWD - REV) / 2.
#
#   research/frieren_r99_e2e_paired.sh [SWEEPS]
set -u
cd "$(dirname "$0")/.." || exit 1

SWEEPS="${1:-6}"
BASE_SHA=c6c66344d9848d95158edc31f31943aabe4de079
P=Sources/MLXFastModel/LagunaRuntimeModel.swift

select_arm() {
    case "$1" in
        base) git checkout "${BASE_SHA}" -- "${P}" || return 1 ;;
        cand) git checkout HEAD -- "${P}" || return 1 ;;
    esac
    /usr/bin/env CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
        swift build -c release --force-resolved-versions \
        --scratch-path .build-worker --product mlxfast-runtime-worker >/dev/null 2>&1
    local s=$?
    git checkout -- Package.resolved 2>/dev/null
    return $s
}

run_arm() {
    local arm="$1" sweep="$2" slot="$3"
    select_arm "${arm}" || { echo "@@BUILDFAIL ${arm}"; return 1; }
    ./benchmark.sh --local-iterate >/tmp/r99_e2e_run.log 2>&1
    local status=$?
    echo "@@RUN sweep=${sweep} slot=${slot} arm=${arm} exit=${status}"
    jq -c '{score: .score,
            decode_spt: .metrics.decode_seconds_per_token,
            prefill_spt: .metrics.prefill_seconds_per_token,
            base_decode_spt: .metrics.baseline_decode_seconds_per_token,
            base_prefill_spt: .metrics.baseline_prefill_seconds_per_token,
            decode_speedup: .metrics.decode_speedup,
            prefill_speedup: .metrics.prefill_speedup,
            passed_correctness: .metrics.passed_correctness,
            golden_hash: .metrics.golden_hash,
            first_failing_case: .metrics.first_failing_case,
            first_failing_step: .metrics.first_failing_step}' \
        score.local-iterate.json 2>/dev/null \
        || echo '{"error":"no score file"}'
    tail -3 /tmp/r99_e2e_run.log
}

for ((i = 1; i <= SWEEPS; i++)); do
    echo "@@SWEEP ${i}"
    if (( i % 2 == 1 )); then
        echo "@@ORDER FWD"
        run_arm base "${i}" 1
        run_arm cand "${i}" 2
    else
        echo "@@ORDER REV"
        run_arm cand "${i}" 1
        run_arm base "${i}" 2
    fi
    echo "@@ENDSWEEP ${i}"
done

echo "=== restore candidate ==="
git checkout HEAD -- "${P}"
select_arm cand
git status --porcelain
echo "DONE"
