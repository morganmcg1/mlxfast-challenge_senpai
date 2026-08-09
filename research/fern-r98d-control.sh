#!/bin/bash
# r98-D preregistered revert-control leg.
#
# Restores the base version of the one submitted file, re-runs the upstream
# equivalence oracle and the local timing screen on it, then puts the candidate
# back. The oracle leg exists because the candidate run failed only on the
# *prefill* step (max abs logit error 0.125, all decode steps exactly 0) while
# the edited kernel is decode-gated; this establishes whether that divergence
# is pre-existing on this non-M5 host.
set -u
cd "$(dirname "$0")/.." || exit 1

BASE=61c8763291e7ee6bd04a1f86f5912193bf3547e6
FILE=Sources/MLXFastModel/LagunaRuntimeModel.swift
OUT=research/artifacts

restore() {
    git checkout HEAD -- "${FILE}"
    echo "RESTORED_CANDIDATE=$(git status --porcelain "${FILE}" | wc -l | tr -d ' ')"
}
trap restore EXIT

git checkout "${BASE}" -- "${FILE}" || exit 1
echo "CONTROL_FILE_SHA=$(git hash-object "${FILE}")"

research/run_upstream_equivalence.sh > "${OUT}/fern-r98d-control-oracle.log" 2>&1
echo "CONTROL_ORACLE_EXIT=$?"
grep -E 'EQUIVALENCE_EXIT|EQUIVALENCE_EXACT_STEPS' "${OUT}/fern-r98d-control-oracle.log"
grep -o '"label" : "prefill"[^}]*' "${OUT}/fern-r98d-control-oracle.log" | head -1

./benchmark.sh --local-iterate
echo "CONTROL_BENCH_EXIT=$?"
cp score.local-iterate.json "${OUT}/fern-r98d-control-B.json"
