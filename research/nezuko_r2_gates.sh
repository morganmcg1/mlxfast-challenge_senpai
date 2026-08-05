#!/usr/bin/env bash
# r2 pre-submission gates for the MLX_MAX_MB_PER_BUFFER=512 arm.
# Sequential on purpose: only one model-holding process at a time.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
run() {
  local name="$1"; shift
  echo "=== ${name} start $(date -u +%H:%M:%S)"
  if "$@"; then
    echo "=== ${name} PASS"
  else
    echo "=== ${name} FAIL rc=$?"
    fail=1
  fi
}

echo "shipped cap token:"
grep -n 'MLX_MAX_MB_PER_BUFFER\|MLX_MAX_OPS_PER_BUFFER' \
  Sources/MLXFastModel/LagunaRuntimeWeights.swift

run upstream_equivalence research/run_upstream_equivalence.sh
run local_iterate ./benchmark.sh --local-iterate

git checkout -- Package.resolved 2>/dev/null || true
echo "=== gates done $(date -u +%H:%M:%S) fail=${fail}"
exit "${fail}"
