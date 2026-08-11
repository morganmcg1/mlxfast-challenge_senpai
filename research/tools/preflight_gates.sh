#!/usr/bin/env bash
# R129-G pre-flight validity gates for a ranked MLXFast fire.
#
# Every gate here is static: no model load, no build, no GPU work, so the whole
# script is seconds and can be run immediately before a submission. The slow
# correctness/token run is deliberately NOT in here (see
# research/r129g_preflight_gates.md §"the slow gate").
#
# Usage:  bash research/tools/preflight_gates.sh [--base-sha <40-hex>]
# Output: one "GATE <name>: PASS|FAIL <reason>" line per gate, then
#         "PREFLIGHT: PASS|FAIL (n/m)". Exit 1 if any gate FAILs.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}" || exit 2

BASE_SHA=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-sha) BASE_SHA="${2:-}"; shift 2 ;;
    --base-sha=*) BASE_SHA="${1#*=}"; shift ;;
    *) echo "preflight: unknown argument '$1'" >&2; exit 2 ;;
  esac
done
[[ -n "${BASE_SHA}" ]] || BASE_SHA="$(git rev-parse HEAD)"

MAX_TOTAL_BYTES=3000000
MAX_FILE_BYTES=524288
# sha256 of the correctness golden fixture every Maple receipt was measured
# against. Overridable because the workflow computes it from the fixture it
# generated (.github/workflows/benchmark.yml:1435).
EXPECTED_GOLDEN_SHA256="${MLXFAST_EXPECTED_CORRECTNESS_GOLDEN_SHA256:-b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63}"
GOLDEN_PATH="${MLXFAST_CORRECTNESS_GOLDEN_PATH:-correctness_golden.json}"

PASS_COUNT=0
FAIL_COUNT=0

gate() { # gate <name> <PASS|FAIL> <reason...>
  local name="$1" verdict="$2"; shift 2
  printf 'GATE %s: %s %s\n' "${name}" "${verdict}" "$*"
  if [[ "${verdict}" == "PASS" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

# Packaged surface: the exact files senpai/check-editable-budget.sh counts.
packaged_files() {
  local entry
  while IFS= read -r entry; do
    [[ -e "${entry}" ]] || continue
    if [[ -f "${entry}" ]]; then
      printf '%s\n' "${entry}"
    else
      find "${entry}" -type f -print
    fi
  done < <(jq -r '.editablePaths[]' benchmark.json)
}

PACKAGED="$(packaged_files)"
PACKAGED_COUNT="$(printf '%s\n' "${PACKAGED}" | grep -c .)"

# ---------------------------------------------------------------- gate: budget
budget_out="$(bash senpai/check-editable-budget.sh "${BASE_SHA}" 2>&1)"
budget_rc=$?
budget_line="$(printf '%s' "${budget_out}" | tr '\n' ' ' | sed 's/  */ /g')"
if [[ ${budget_rc} -eq 0 ]]; then
  gate budget PASS "${budget_line}"
else
  gate budget FAIL "rc=${budget_rc} ${budget_line}"
fi

# --------------------------------------------------------------- gate: perfile
worst_line="$(printf '%s\n' "${PACKAGED}" | tr '\n' '\0' | xargs -0 wc -c 2>/dev/null \
  | grep -v ' total$' | sort -n | tail -1)"
worst_bytes="$(printf '%s' "${worst_line}" | awk '{print $1}')"
worst_file="$(printf '%s' "${worst_line}" | awk '{$1=""; sub(/^ /,""); print}')"
if (( worst_bytes >= MAX_FILE_BYTES )); then
  gate perfile FAIL "${worst_file} is ${worst_bytes} B >= cap ${MAX_FILE_BYTES} B (files=${PACKAGED_COUNT})"
else
  gate perfile PASS "largest packaged file ${worst_file} ${worst_bytes} B < cap ${MAX_FILE_BYTES} B (files=${PACKAGED_COUNT})"
fi

# ------------------------------------------------------------- gate: tree_clean
DIRTY="$(jq -r '.editablePaths[]' benchmark.json | tr '\n' '\0' \
  | xargs -0 git status --porcelain -- 2>/dev/null)"
dirty_count="$(printf '%s\n' "${DIRTY}" | grep -c .)"
if (( dirty_count > 0 )); then
  gate tree_clean FAIL "${dirty_count} uncommitted change(s) in the packaged surface: $(printf '%s' "${DIRTY}" | head -1)"
else
  gate tree_clean PASS "packaged surface matches HEAD $(git rev-parse --short HEAD), no uncommitted or untracked packaged files"
fi

# ---------------------------------------------------------------- gate: refuted
refuted_named="$(printf '%s\n' "${PACKAGED}" | grep "REFUTED_DO_NOT_LAND" | tr '\n' ' ')"
refuted_marked="$(printf '%s\n' "${PACKAGED}" | tr '\n' '\0' \
  | xargs -0 grep -l "REFUTED_DO_NOT_LAND" 2>/dev/null | tr '\n' ' ')"
if [[ -n "${refuted_named}${refuted_marked}" ]]; then
  gate refuted FAIL "refuted patch present in packaged surface: named=[${refuted_named}] marker=[${refuted_marked}]"
else
  gate refuted PASS "no REFUTED_DO_NOT_LAND file or marker in ${PACKAGED_COUNT} packaged files"
fi

# ------------------------------------------------------- gate: startup_profile
# RuntimeStartupMemoryPolicy.resolve: unset/auto -> low below 64 GiB; an illegal
# value is a preconditionFailure, i.e. a crashed ranked run.
mem_bytes="$(sysctl -n hw.memsize)"
mem_gib=$((mem_bytes >> 30))
profile_raw="${DARKBLOOM_STARTUP_MEMORY_PROFILE-<unset>}"
profile="$(printf '%s' "${profile_raw}" | tr '[:upper:]' '[:lower:]')"
case "${profile}" in
  full) gate startup_profile PASS "override=full -> full profile on a ${mem_gib} GiB host" ;;
  low)  gate startup_profile FAIL "override=low forces the low-memory profile; ranked behavior needs full" ;;
  ""|"<unset>"|auto)
    if (( mem_bytes >= (64 << 30) )); then
      gate startup_profile PASS "override=${profile_raw} resolves to full: ${mem_gib} GiB >= 64 GiB minimum"
    else
      gate startup_profile FAIL "override=${profile_raw} resolves to LOW on this ${mem_gib} GiB host; export DARKBLOOM_STARTUP_MEMORY_PROFILE=full"
    fi ;;
  *) gate startup_profile FAIL "illegal value '${profile_raw}': resolve() preconditionFailure will abort the run (legal: auto|full|low)" ;;
esac

# ------------------------------------------------------------- gate: qmv_fused
fused="${DARKBLOOM_SHARED_ROUTED_QMV_FUSED-<unset>}"
case "${fused}" in
  "<unset>"|0|false|no) gate qmv_fused PASS "DARKBLOOM_SHARED_ROUTED_QMV_FUSED=${fused} (off; on costs +55.2 us/step, #733)" ;;
  *) gate qmv_fused FAIL "DARKBLOOM_SHARED_ROUTED_QMV_FUSED=${fused} enables the measured +55.2 us/step regression (#733)" ;;
esac

# ------------------------------------------------------------------- gate: nax
# is_nax_available() needs macOS >= 26.2 AND Apple GPU generation >= 17
# (Vendor/mlx-swift/.../backend/metal/device.cpp). Apple GPU gen = 12 + M-series
# family, so M4 Pro = 16 and cannot select _nax; an M5 host can.
chip="$(sysctl -n machdep.cpu.brand_string)"
os_ver="$(sw_vers -productVersion)"
family="$(printf '%s' "${chip}" | sed -n 's/^Apple M\([0-9][0-9]*\).*/\1/p')"
os_major="${os_ver%%.*}"
os_minor="$(printf '%s' "${os_ver}" | cut -d. -f2)"
if [[ -z "${family}" ]]; then
  gate nax FAIL "cannot parse Apple M-series family from '${chip}'; GPU generation unknown"
else
  gpu_gen=$((12 + family))
  os_ok=0
  if (( os_major > 26 )) || { (( os_major == 26 )) && (( ${os_minor:-0} >= 2 )); }; then os_ok=1; fi
  if (( gpu_gen >= 17 )) && (( os_ok == 1 )); then
    gate nax FAIL "${chip} is GPU gen ${gpu_gen} on macOS ${os_ver}: is_nax_available() is TRUE, so _nax kernels are selected and this is not the gen-16 student-host regime"
  else
    gate nax PASS "${chip} = GPU gen ${gpu_gen}, macOS ${os_ver}: is_nax_available() false, no _nax kernels selected"
  fi
fi

# ---------------------------------------------------------------- gate: golden
if [[ ! -s "${GOLDEN_PATH}" ]]; then
  gate golden FAIL "correctness golden missing or empty at ${GOLDEN_PATH}; no correctness gate can run on this host"
else
  actual_hash="$(shasum -a 256 "${GOLDEN_PATH}" | awk '{print $1}')"
  if [[ "${actual_hash}" == "${EXPECTED_GOLDEN_SHA256}" ]]; then
    gate golden PASS "${GOLDEN_PATH} sha256=${actual_hash} matches the expected fixture"
  else
    gate golden FAIL "${GOLDEN_PATH} sha256=${actual_hash} != expected ${EXPECTED_GOLDEN_SHA256}"
  fi
fi

total=$((PASS_COUNT + FAIL_COUNT))
if (( FAIL_COUNT > 0 )); then
  printf 'PREFLIGHT: FAIL (%d/%d)\n' "${PASS_COUNT}" "${total}"
  exit 1
fi
printf 'PREFLIGHT: PASS (%d/%d)\n' "${PASS_COUNT}" "${total}"
