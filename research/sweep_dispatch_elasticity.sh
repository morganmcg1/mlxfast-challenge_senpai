#!/bin/bash
# Research-only. Prices one decode kernel family by perturbing only its GPU
# work and reading the change in per-step wall and gpu_busy_union.
#
#   research/sweep_dispatch_elasticity.sh <steps> <split> <spec> [spec ...]
#
# spec is `mode:substring`; mode is one of
#   base  no injection (reference arm)
#   dup   every matching dispatch is issued twice, barrier-separated
#         (synthetic slowdown, +1x that family's serial GPU time)
#   skip  every matching dispatch is dropped, leaving the barrier, command
#         buffer boundaries and all host encode work in place
#         (synthetic speedup, -1x that family's GPU time)
#
# skip and dup change decoded tokens; the arms are throwaway instruments and
# the reported divergence count is expected to be nonzero for them.
cd "$(dirname "$0")/.." || exit 1
STEPS="${1:-150}"
SPLIT="${2:-0}"
shift 2 2>/dev/null
SPECS=("$@")
if [ ${#SPECS[@]} -eq 0 ]; then
    SPECS=(base:)
fi

for spec in "${SPECS[@]}"; do
    mode="${spec%%:*}"
    pattern="${spec#*:}"
    dup=""
    skip=""
    case "$mode" in
        base) pattern="" ;;
        dup) dup="${pattern}" ;;
        skip) skip="${pattern}" ;;
        *) echo "unknown mode ${mode}"; exit 1 ;;
    esac
    tag="${mode}${pattern:+-}${pattern}"
    echo "================ ${mode} ${pattern} SPLIT=${SPLIT} STEPS=${STEPS} ================"
    err="/tmp/elastic.${tag}.split${SPLIT}.err"
    DARKBLOOM_GPU_DUP="${dup}" \
    DARKBLOOM_GPU_SKIP="${skip}" \
    DARKBLOOM_GPU_PROFILE=1 \
    DARKBLOOM_GPU_PROFILE_SPLIT="${SPLIT}" \
        python3 research/decode_probe.py --steps "${STEPS}" --profile \
            --profile-top 24 --stderr "${err}" 2>&1 \
        | grep -Ev "^ *$" \
        | grep -E 'worker up|divergences|per steady step|profile:'
    # A typo'd substring binds nothing and looks exactly like a null result.
    grep -c 'GPUINJECT' "${err}" | sed 's/^/  injected pipelines: /'
    grep 'GPUINJECT' "${err}" | sort -u | sed 's/^/  /'
    echo
done
echo SWEEP_DONE
