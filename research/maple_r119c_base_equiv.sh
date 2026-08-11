#!/usr/bin/env bash
# Research-only (PR #714, R119-C): run the upstream-equivalence oracle against
# the assignment base's LagunaRuntimeModel.swift, to establish whether this
# M4 Pro host's prefill logit divergence pre-dates the R119-C arms.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

BASE="${BASE:-cd047c00fae93176c93600966d7c542cc836cdc8}"
OUT="${OUT:-research/r119c-runs/correctness}"
FILE="Sources/MLXFastModel/LagunaRuntimeModel.swift"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty" >&2
  exit 2
fi

restore() {
  git checkout HEAD -- "${FILE}"
  echo "### restored ${FILE} to HEAD"
}
git checkout "${BASE}" -- "${FILE}" || exit 3
trap restore EXIT
echo "### base ${BASE} runtime file in place; HEAD=$(git rev-parse HEAD)"

bash research/run_upstream_equivalence.sh >"${OUT}/equiv-base.log" 2>&1
echo "--- rc=$?"
grep -E "EQUIVALENCE_EXACT_STEPS|EQUIVALENCE_EXIT" "${OUT}/equiv-base.log"
grep -o 'maximumAbsoluteLogitError: [0-9.e-]*' "${OUT}/equiv-base.log" \
  | tr '\n' ' '
echo
