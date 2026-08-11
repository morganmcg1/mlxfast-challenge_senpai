#!/usr/bin/env bash
# R129-G negative controls: one injected defect per gate in research/tools/preflight_gates.sh.
# Nothing here touches the tracked tree; file defects go into a detached git
# worktree under TMPDIR that is removed at the end.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_SHA="9f7cafdad608993ea97b901aa2f87d3dcb2d7d5f"
SCRATCH="${TMPDIR:-/tmp}/r129g-scratch"
GATES="research/tools/preflight_gates.sh"

cd "${REPO_ROOT}" || exit 2
rm -rf "${SCRATCH}"
git worktree remove --force "${SCRATCH}" 2>/dev/null
git worktree add --detach "${SCRATCH}" HEAD >/dev/null 2>&1 || { echo "scratch worktree failed"; exit 2; }
# the gate script is not committed yet, and research/ is not a packaged path, so
# copying it into the scratch worktree cannot perturb any gate
mkdir -p "${SCRATCH}/research/tools"
cp "${GATES}" "${SCRATCH}/${GATES}"

run_scratch() { # run_scratch <label> <gate-name-filter>
  local label="$1" filter="$2"
  echo "--- CONTROL ${label}"
  ( cd "${SCRATCH}" && DARKBLOOM_STARTUP_MEMORY_PROFILE=full bash "${GATES}" --base-sha "${BASE_SHA}" \
      | grep -E "GATE (${filter}):|PREFLIGHT:" ; echo "exit=${PIPESTATUS[0]}" )
}

echo "=== CONTROL 1: budget (total over headroom 287510, under per-file cap)"
mkdir -p "${SCRATCH}/Sources/MLXFastModel"
dd if=/dev/zero bs=1000 count=400 2>/dev/null | tr '\0' 'x' > "${SCRATCH}/Sources/MLXFastModel/InjectedBudget.swift"
run_scratch budget "budget|perfile"
rm -f "${SCRATCH}/Sources/MLXFastModel/InjectedBudget.swift"

echo "=== CONTROL 2: perfile (single file at 600000 B >= 524288 cap)"
dd if=/dev/zero bs=1000 count=600 2>/dev/null | tr '\0' 'x' > "${SCRATCH}/Sources/MLXFastModel/InjectedBig.swift"
run_scratch perfile "perfile"
rm -f "${SCRATCH}/Sources/MLXFastModel/InjectedBig.swift"

echo "=== CONTROL 3: tree_clean (uncommitted edit to a packaged file)"
printf '\n// injected uncommitted edit\n' >> "${SCRATCH}/Sources/MLXFastModel/LagunaRuntimeModel.swift"
run_scratch tree_clean "tree_clean"
( cd "${SCRATCH}" && git checkout -- Sources/MLXFastModel/LagunaRuntimeModel.swift )

echo "=== CONTROL 4: refuted (REFUTED_DO_NOT_LAND patch inside the packaged surface)"
printf 'threadgroup width 64 -> 256 SwiGLU QMV delta\n' > "${SCRATCH}/Sources/MLXFastModel/REFUTED_DO_NOT_LAND_tg256_swiglu_qmv.patch"
run_scratch refuted "refuted"
rm -f "${SCRATCH}/Sources/MLXFastModel/REFUTED_DO_NOT_LAND_tg256_swiglu_qmv.patch"

echo "=== CONTROL 5a: startup_profile (override=low)"
DARKBLOOM_STARTUP_MEMORY_PROFILE=low bash "${GATES}" --base-sha "${BASE_SHA}" | grep -E "GATE startup_profile:|PREFLIGHT:"
echo "exit=${PIPESTATUS[0]}"
echo "=== CONTROL 5b: startup_profile (illegal value 'ful' -> preconditionFailure)"
DARKBLOOM_STARTUP_MEMORY_PROFILE=ful bash "${GATES}" --base-sha "${BASE_SHA}" | grep -E "GATE startup_profile:|PREFLIGHT:"
echo "exit=${PIPESTATUS[0]}"
echo "=== CONTROL 5c: startup_profile (unset on this 48 GiB host -> resolves LOW)"
bash "${GATES}" --base-sha "${BASE_SHA}" | grep -E "GATE startup_profile:|PREFLIGHT:"
echo "exit=${PIPESTATUS[0]}"

echo "=== CONTROL 6: qmv_fused (=1)"
DARKBLOOM_STARTUP_MEMORY_PROFILE=full DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1 bash "${GATES}" --base-sha "${BASE_SHA}" \
  | grep -E "GATE qmv_fused:|PREFLIGHT:"
echo "exit=${PIPESTATUS[0]}"

echo "=== CONTROL 7: nax (scratch copy of the gate script with the parsed family forced to 5, i.e. an M5-class host)"
FAKE="research/tools/.r129g-gates-fakem5.sh"
sed 's|^family="\$(printf.*|family="5"|' "${GATES}" > "${FAKE}"
( cd "${REPO_ROOT}" && DARKBLOOM_STARTUP_MEMORY_PROFILE=full bash "${FAKE}" --base-sha "${BASE_SHA}" \
    | grep -E "GATE nax:|PREFLIGHT:" ; echo "exit=${PIPESTATUS[0]}" )

echo "=== CONTROL 8a: golden (expected hash provided, file matches -> PASS path)"
GOOD="${TMPDIR:-/tmp}/r129g-golden-good.json"
printf '{"correctness_gates":{}}\n' > "${GOOD}"
GOOD_SHA="$(shasum -a 256 "${GOOD}" | awk '{print $1}')"
DARKBLOOM_STARTUP_MEMORY_PROFILE=full MLXFAST_CORRECTNESS_GOLDEN_PATH="${GOOD}" \
  MLXFAST_EXPECTED_CORRECTNESS_GOLDEN_SHA256="${GOOD_SHA}" bash "${GATES}" --base-sha "${BASE_SHA}" \
  | grep -E "GATE golden:|PREFLIGHT:"
echo "exit=${PIPESTATUS[0]}"
echo "=== CONTROL 8b: golden (one byte changed -> FAIL path)"
printf '{"correctness_gates":{}} \n' > "${GOOD}"
DARKBLOOM_STARTUP_MEMORY_PROFILE=full MLXFAST_CORRECTNESS_GOLDEN_PATH="${GOOD}" \
  MLXFAST_EXPECTED_CORRECTNESS_GOLDEN_SHA256="${GOOD_SHA}" bash "${GATES}" --base-sha "${BASE_SHA}" \
  | grep -E "GATE golden:|PREFLIGHT:"
echo "exit=${PIPESTATUS[0]}"

rm -f "${GOOD}" "${FAKE}"
git worktree remove --force "${SCRATCH}" >/dev/null 2>&1
echo "=== controls done; scratch removed"
