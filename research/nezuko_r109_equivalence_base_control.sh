#!/bin/bash
# Base control for the upstream-equivalence oracle.
#
# research/run_upstream_equivalence.sh on this M4 host reports every greedy
# token matching upstream and all eight decode steps bit-exact, but the single
# 512-token prefill step differs by 0.125 max / 0.0119 mean absolute logit
# error, which fails the oracle's exact (tolerance 0) gate. The oracle is
# documented as an M5 operator gate (docs/laguna-weight-contract.md:168,
# "operators invoke its gated test on the M5"), so before attributing that
# prefill delta to the assignment this script re-runs the identical oracle
# against BASE_SHA's Sources and nothing else.
#
# Only two files are in this assignment's submitted surface, so restoring both
# to BASE_SHA makes the built runtime byte-identical to the research base;
# research/ and docs/ do not enter the build. CONTROL_DIFF_VS_BASE must print
# no rows for that claim to hold, and the EXIT trap puts HEAD's Sources back.
cd "$(dirname "$0")/.." || exit 1
BASE="${1:-1a6761bf46c282fcabd0577b618f0c1206757e6c}"
RT=Sources/MLXFastModel/LagunaRuntimeModel.swift
NEW=Sources/MLXFastModel/LagunaNormFusedGateSoftplus.swift

if [ -n "$(git status --porcelain -- Sources)" ]; then
    echo "control: Sources already dirty; refusing to swap" >&2
    exit 2
fi

restore() {
    git checkout HEAD -- "$RT" "$NEW"
    echo "CONTROL_SOURCES_DIRTY_AFTER_RESTORE=$(
        git status --porcelain -- Sources | wc -l | tr -d ' ')"
}
trap restore EXIT

git checkout "$BASE" -- "$RT" || exit 2
rm -f "$NEW" || exit 2
echo "CONTROL_BASE=${BASE}"
git diff --numstat "$BASE" -- Sources | sed 's/^/CONTROL_DIFF_VS_BASE: /'

bash research/run_upstream_equivalence.sh
status=$?
echo "CONTROL_EXIT=${status}"
exit "${status}"
