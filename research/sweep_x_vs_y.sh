#!/usr/bin/env bash
# Research-only wrapper (not part of the submission).
#
# ABBA-blocked local A/B between the two *source trees* of this arm:
#
#   X = BASE_SHA - 9c1ad1c - 6ca0c71          (commit 6d14ed9, Part 1a only)
#   Y = X + the M1 LM-head cascade            (the branch tip)
#
# The earlier 8-arm A/B toggled DARKBLOOM_LMHEAD_FUSED_REFINEMENT on one
# binary, so its control still carried the new plane packing and the _v6
# kernel -- "refinement off", not "pre-M1". This script switches the tree
# instead, so the control really is pre-M1. Each arm rebuilds; benchmark.sh
# detects the stale worker itself.
#
# Order XYYX cancels linear session drift to first order.
set -euo pipefail

cd "$(dirname "$0")/.."

X_COMMIT=6d14ed9
TIP="$(git rev-parse HEAD)"
OUT=/tmp/ab-x
mkdir -p "${OUT}"

restore() { git checkout "${TIP}" -- Sources Vendor; }
trap restore EXIT

run_arm() {
    local arm="$1" tag="$2" commit
    case "${arm}" in
        X) commit="${X_COMMIT}" ;;
        Y) commit="${TIP}" ;;
        *) echo "unknown arm ${arm}" >&2; return 1 ;;
    esac
    git checkout "${commit}" -- Sources Vendor
    echo "=== arm ${arm} tag ${tag} tree ${commit} $(date -u +%H:%M:%S) ==="
    research/run_local_benchmark.sh --local-iterate
    cp score.json "${OUT}/score.${arm}.${tag}.json"
    date -u +%s > "${OUT}/t.${arm}.${tag}"
}

run_arm X 1
run_arm Y 1
run_arm Y 2
run_arm X 2

echo "=== done; artifacts in ${OUT} ==="
