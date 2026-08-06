#!/bin/bash
# Campaign A: within-binary A/B on DARKBLOOM_DENSE_PACKED, one build, no
# checkout or rebuild between runs, so the two arms differ only by whether the
# packed banks are built and dispatched. The OFF arm takes the identical stock
# `lagunaFusedDenseGateUpSwiGLUEnabled` path the unchanged base takes.
#
# Order is counterbalanced: balanced 6/6, balanced 3/3 within each half, and
# never more than two consecutive runs on one arm.
set -u
cd "$(dirname "$0")/../.." || exit 1
OUT=/tmp/nezuko85/campaign-a
mkdir -p "$OUT"
unset DARKBLOOM_TRACE_FUSION
i=0
for arm in on off off on off on on off on off off on; do
    i=$((i + 1))
    if [ "$arm" = off ]; then
        export DARKBLOOM_DENSE_PACKED=0
    else
        unset DARKBLOOM_DENSE_PACKED
    fi
    echo "=== campaign A slot $i arm $arm $(date -u +%H:%M:%S) ==="
    rm -f score.local-iterate.json
    ./benchmark.sh --local-iterate 2>&1 | tail -6
    cp score.local-iterate.json "$OUT/a_$(printf %02d "$i")_${arm}.json" || exit 1
done
echo "=== campaign A complete ==="
