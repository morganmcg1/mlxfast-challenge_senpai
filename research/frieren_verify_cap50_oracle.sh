#!/usr/bin/env bash
# Research-only: run the vendored-Laguna upstream-equivalence oracle twice, once
# under the host's own (low-memory) startup profile for comparability with the
# recorded reference, and once with the full profile so the 50 MiB command-buffer
# cap under test is actually the setting in force.
set -uo pipefail

cd "$(dirname "$0")/.."

echo "=== ORACLE stock profile (low-memory on this 48 GiB host) ==="
research/run_upstream_equivalence.sh
echo "=== ORACLE stock profile exit=$? ==="

echo "=== ORACLE full profile (cap under test in force) ==="
DARKBLOOM_STARTUP_MEMORY_PROFILE=full research/run_upstream_equivalence.sh
echo "=== ORACLE full profile exit=$? ==="

git checkout -- Package.resolved
