#!/usr/bin/env bash
# Research-only (PR #558, R100-C): run the vendored-Laguna upstream-equivalence
# oracle once per DARKBLOOM_ROUTER_WEIGHT_PREFETCH arm.
#
#   bash research/maple-nezuko-r100c-equivalence-ab.sh OUTDIR [ARM...]
#
# The runtime default is 1, so the pf0 leg MUST set the variable explicitly;
# this script always exports it, for every arm. research/run_upstream_equiv-
# alence.sh already refuses to call a zero-test invocation a pass, so the exit
# code plus the EQUIVALENCE_EXACT_STEPS count is the whole verdict.
set -uo pipefail

OUT="${1:?usage: OUTDIR [ARM...]}"
shift || true
ARMS=("$@")
[ "${#ARMS[@]}" -gt 0 ] && : || ARMS=(0 1)
mkdir -p "${OUT}"

printf 'head=%s\n' "$(git rev-parse HEAD)" | tee "${OUT}/provenance.txt"

fail=0
for arm in "${ARMS[@]}"; do
  echo "=== equivalence pf${arm} starting $(date -u +%H:%M:%SZ) ==="
  env DARKBLOOM_ROUTER_WEIGHT_PREFETCH="${arm}" \
    bash research/run_upstream_equivalence.sh > "${OUT}/pf${arm}.log" 2>&1
  rc=$?
  git checkout -- Package.resolved 2>/dev/null || true
  steps="$(grep -o 'EQUIVALENCE_EXACT_STEPS=[0-9]*' "${OUT}/pf${arm}.log" \
    | tail -1)"
  tests="$(grep -Eo 'Test run with [0-9]+ test' "${OUT}/pf${arm}.log" | tail -1)"
  printf 'pf%s rc=%s %s %s\n' "${arm}" "${rc}" "${steps:-NO_STEP_MARKER}" \
    "${tests:-NO_TEST_COUNT}" | tee -a "${OUT}/summary.txt"
  [ "${rc}" -eq 0 ] || { fail=1; tail -30 "${OUT}/pf${arm}.log" \
    | tee -a "${OUT}/summary.txt"; }
done

echo "########## equivalence fail=${fail} ##########" | tee -a "${OUT}/summary.txt"
exit "${fail}"
