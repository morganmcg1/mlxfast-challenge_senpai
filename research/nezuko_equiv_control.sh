#!/usr/bin/env bash
# Attribution control for the upstream-equivalence prefill delta seen on this
# M4 host at MLX_MAX_MB_PER_BUFFER=512.
#
# run_upstream_equivalence.sh prescribes comparing the unchanged BASE_SHA on a
# non-M5 host before attributing drift. The runtime sets the cap with
# setenv(..., overwrite=0), so an exported MLX_MAX_MB_PER_BUFFER wins and
# reproduces any cap's behaviour from the same binary with no rebuild:
#   200 = the unchanged BASE_SHA value, 50 = the r1 arm, 512 = the r2 arm.
set -uo pipefail
cd "$(dirname "$0")/.."

for mb in 200 50 512; do
  echo "=== equivalence cap=${mb} start $(date -u +%H:%M:%S)"
  MLX_MAX_MB_PER_BUFFER="${mb}" research/run_upstream_equivalence.sh 2>&1 \
    | grep -E '"label"|maximumAbsoluteLogitError|meanAbsoluteLogitError|runtimeToken|upstreamToken|EQUIVALENCE_' \
    | sed "s/^/cap=${mb} /"
  echo "=== equivalence cap=${mb} done $(date -u +%H:%M:%S)"
done

git checkout -- Package.resolved 2>/dev/null || true
