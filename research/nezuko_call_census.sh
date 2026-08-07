#!/usr/bin/env bash
# Reachability census for the two decode attention dispatch sites this PR
# modifies (advisor feedback #5, standing rule 1: "no null result is
# interpretable until the arm ships a call-count census proving the
# instrumented site actually executes on the scored path").
#
# Requires the temporary `lagunaCensus` counter in LagunaRuntimeModel.swift,
# which writes one stderr line per dispatch under DARKBLOOM_CALL_CENSUS=1.
# That counter is research-only and is reverted before submission; this script
# is kept so the census is reproducible from the recorded commit pair.
#
#   OUT=/tmp/nez_census STEPS=128 bash research/nezuko_call_census.sh
#
# Every model-holding run must be the only one on the host.
set -u

OUT="${OUT:-/tmp/nez_census}"
STEPS="${STEPS:-128}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO}" || exit 1
mkdir -p "${OUT}" .build-worker/clang-module-cache

echo "REPO=${REPO}"
echo "HEAD=$(git rev-parse HEAD)"
echo "SRC_MD5=$(md5 -q Sources/MLXFastModel/LagunaRuntimeModel.swift)"
echo "STEPS=${STEPS}"

CLANG_MODULE_CACHE_PATH="${REPO}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    >"${OUT}/build.log" 2>&1
echo "BUILD_RC=$?"
git checkout -- Package.resolved 2>/dev/null

DARKBLOOM_CALL_CENSUS=1 DARKBLOOM_TRACE_FUSION=1 \
    python3 research/decode_probe.py --steps "${STEPS}" \
    --stderr "${OUT}/worker.err" >"${OUT}/probe.log" 2>&1
echo "PROBE_RC=$?"

echo "--- census: dispatches per site, whole worker lifetime ---"
grep '^mlxfast: CENSUS ' "${OUT}/worker.err" \
    | sed 's/^mlxfast: CENSUS //' | sort | uniq -c
echo "--- first-touch fusion trace ---"
grep '^mlxfast: fusion active' "${OUT}/worker.err" | sort
echo "--- probe summary ---"
grep -E 'decode steps=|divergen' "${OUT}/probe.log"
echo "CENSUS_DONE"
