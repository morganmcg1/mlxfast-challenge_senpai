#!/usr/bin/env bash
# R97-B P2b gate: rebuild the worker, take the exact-token correctness verdict
# with DARKBLOOM_FUSED_QKV both off and on, then take the dispatch census that
# decides whether the 78 strided copies are actually gone.
set -uo pipefail
cd "$(dirname "$0")/.."

research/tanjiro-r97-ab.sh 1
echo "r97-p2b-gate: ab exit=$?"

research/tanjiro-r97-census.sh
echo "r97-p2b-gate: census exit=$?"
