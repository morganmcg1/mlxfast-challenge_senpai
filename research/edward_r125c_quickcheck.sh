#!/usr/bin/env bash
# R125-C fast reachability + token-identity check across the routed gate/up QMV
# threads-per-threadgroup ladder. One model-holding process at a time.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

OUT=${OUT:-/tmp/r125c-quick}
mkdir -p "${OUT}"
export PATH="${HOME}/.local/bin:${PATH}"
export MLXFAST_LOCAL_FAN_PROMPT=0

for tg in 64 128 256; do
    echo "### tg=${tg} teacher-forced $(date -u +%H:%M:%SZ)"
    DARKBLOOM_ROUTED_QMV_TG="${tg}" DARKBLOOM_TRACE_FUSION=1 \
        python3 research/decode_probe.py --steps 64 \
        --dump-tokens "${OUT}/tf_${tg}.txt" \
        --stderr "${OUT}/err_tf_${tg}.log" 2>&1 | tail -5
    echo "TRACE tg=${tg}:"
    grep -o 'fusion active: .*' "${OUT}/err_tf_${tg}.log" | sort -u | sed 's/^/TRACE /'

    echo "### tg=${tg} free-run $(date -u +%H:%M:%SZ)"
    DARKBLOOM_ROUTED_QMV_TG="${tg}" \
        python3 research/decode_probe.py --steps 64 --free-run \
        --free-run-bootstrap 1547 \
        --dump-tokens "${OUT}/fr_${tg}.txt" \
        --stderr "${OUT}/err_fr_${tg}.log" 2>&1 | tail -4
done

echo "### token identity vs tg=64"
for tg in 128 256; do
    for kind in tf fr; do
        if cmp -s "${OUT}/${kind}_64.txt" "${OUT}/${kind}_${tg}.txt"; then
            echo "IDENTITY ${kind} tg${tg} vs tg64: IDENTICAL"
        else
            echo "IDENTITY ${kind} tg${tg} vs tg64: DIFFER"
            diff "${OUT}/${kind}_64.txt" "${OUT}/${kind}_${tg}.txt" | head -10
        fi
    done
done
echo "### done $(date -u +%H:%M:%SZ)"
