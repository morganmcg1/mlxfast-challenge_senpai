#!/usr/bin/env bash
# R106-B: the pre-handoff verification suite, run once at the final commit.
#
# Everything a reviewer of PR #616 would run before trusting the branch, in one
# place, with every check's exit status reported explicitly rather than being
# swallowed by an early `set -e`.  This exists because the round recommends
# adopting ZERO source bytes (report SS G.1): the branch still carries
# default-off measurement kernels, so it must be demonstrated that carrying them
# breaks nothing -- tests pass, the editable surface is respected, the tree
# builds from scratch.
#
# Usage: research/maple-nezuko-r106b-verify-handoff.sh [outdir]
set -uo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-/tmp/r106b-verify}"
mkdir -p "${OUT}"

BASE_SHA="${BASE_SHA:-446fe9875d1f95b1216628b5809a99da844e5c79}"
HEAD_SHA="$(git rev-parse HEAD)"
export BASE_SHA HEAD_SHA

echo "=== R106-B pre-handoff verification ==="
echo "date:     $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "base:     ${BASE_SHA}"
echo "head:     ${HEAD_SHA}"
echo "worktree: $(git status --porcelain | wc -l | tr -d ' ') modified path(s)"
echo "outdir:   ${OUT}"
echo

rc_dirty=0
if [[ -n "$(git status --porcelain)" ]]; then
  echo "!! worktree is NOT clean; the checks below do not describe ${HEAD_SHA}"
  rc_dirty=1
fi

step() { printf '\n----- [%s] %s -----\n' "$1" "$2"; }

# ---------------------------------------------------------------- 1. surface
step 1 "modifiable surface (CI gate: .github/scripts/enforce-modifiable-surface.sh)"
.github/scripts/enforce-modifiable-surface.sh >"${OUT}/surface.log" 2>&1
rc_surface=$?
tail -20 "${OUT}/surface.log"
echo "exit=${rc_surface}"

# ---------------------------------------------------------- 2. editable budget
step 2 "editable-surface budget (senpai/check-editable-budget.sh)"
senpai/check-editable-budget.sh "${BASE_SHA}" >"${OUT}/budget.log" 2>&1
rc_budget=$?
tail -20 "${OUT}/budget.log"
echo "exit=${rc_budget}"

# ------------------------------------------------------------ 3. source digest
step 3 "Sources/ digest vs base (section E.1 of the report)"
research/maple-nezuko-r106b-surface.sh >"${OUT}/digest.log" 2>&1
rc_digest=$?
cat "${OUT}/digest.log"
echo "exit=${rc_digest}"

# -------------------------------------------------------------- 4. clean build
step 4 "clean release build (rm -rf .build then swift build -c release)"
rm -rf .build
swift build -c release --force-resolved-versions >"${OUT}/build.log" 2>&1
rc_build=$?
tail -20 "${OUT}/build.log"
echo "exit=${rc_build}"

# --------------------------------------------------------------- 5. swift test
step 5 "swift test --force-resolved-versions"
swift test --force-resolved-versions >"${OUT}/test.log" 2>&1
rc_test=$?
tail -30 "${OUT}/test.log"
echo "exit=${rc_test}"

# ------------------------------------------------------------- 6. default gate
# The adoption recommendation is zero bytes, which is only honest if the shipped
# DEFAULT path is still the untouched baseline kernel.  Inventory every gate this
# round added and show each one is read as opt-in (absent env var => false).
step 6 "default-off inventory: gates added and kernel variants compiled"
{
  echo "-- kernel names present in Sources/ --"
  grep -rho 'laguna_sliding_fused_attn_ring[a-z0-9_]*' Sources/ | sort -u
  echo
  echo "-- DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED* env reads --"
  grep -rn 'DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED' Sources/ || true
} >"${OUT}/gates.log" 2>&1
rc_gates=$?
cat "${OUT}/gates.log"
echo "exit=${rc_gates}"

# ------------------------------------------------------------------- summary
printf '\n===== SUMMARY =====\n'
printf 'dirty_worktree        %s\n' "${rc_dirty}"
printf 'enforce_surface       %s\n' "${rc_surface}"
printf 'editable_budget       %s\n' "${rc_budget}"
printf 'source_digest         %s\n' "${rc_digest}"
printf 'clean_release_build   %s\n' "${rc_build}"
printf 'swift_test            %s\n' "${rc_test}"
printf 'gate_inventory        %s\n' "${rc_gates}"

fail=$(( rc_dirty + rc_surface + rc_budget + rc_build + rc_test ))
if (( fail == 0 )); then
  echo "VERIFY: OK (all blocking checks passed at ${HEAD_SHA})"
else
  echo "VERIFY: FAIL (${fail} blocking failure unit(s)) -- see ${OUT}/*.log"
fi
exit "${fail}"
