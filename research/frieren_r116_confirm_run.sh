#!/usr/bin/env bash
# R116-A confirmation stage runner. Design is fixed by
# research/frieren_r116_confirm_prereg.md; this script only executes it.
#
#   frieren_r116_confirm_run.sh FIRST_BLOCK LAST_BLOCK
#
# Writes every artifact outside the git checkout so a running job cannot
# dirty the worktree. Re-running skips blocks whose score JSON already
# exists, so a timed-out job resumes where it stopped.
set -uo pipefail

FIRST="${1:?first block}"
LAST="${2:?last block}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${MLXFAST_R116_OUT:-$(cd "${REPO}/.." && pwd)/r116-confirm}"
mkdir -p "${OUT}"

# arm -> extra environment assignment ("" for the control)
arm_env() {
  case "$1" in
    ctl) printf '' ;;
    qmvse0) printf 'DARKBLOOM_NVFP4_QMV_SEED_ELIDE=0' ;;
    qmvsc0) printf 'DARKBLOOM_NVFP4_QMV_SIGN_CARRY=0' ;;
    sc0) printf 'DARKBLOOM_NVFP4_SCALE_CARRY=0' ;;
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}

FORWARD=(ctl qmvse0 qmvsc0 sc0)
REVERSE=(sc0 qmvsc0 qmvse0 ctl)

for ((b = FIRST; b <= LAST; b++)); do
  if ((b % 2 == 1)); then
    order=("${FORWARD[@]}")
  else
    order=("${REVERSE[@]}")
  fi
  for arm in "${order[@]}"; do
    score="${OUT}/score-${arm}-b${b}.json"
    log="${OUT}/log-${arm}-b${b}.txt"
    if [[ -s "${score}" ]]; then
      echo "[$(date -u +%H:%M:%SZ)] skip ${arm} b${b} (already present)"
      continue
    fi
    echo "[$(date -u +%H:%M:%SZ)] run ${arm} b${b}"
    extra="$(arm_env "${arm}")"
    (
      cd "${REPO}" || exit 1
      export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
      export MLXFAST_SCORE_PATH="${score}"
      if [[ -n "${extra}" ]]; then
        export "${extra?}"
      fi
      ./benchmark.sh --local-iterate
    ) >"${log}" 2>&1
    rc=$?
    notices=$(grep -c 'low-memory\|low memory startup profile' "${log}" 2>/dev/null || echo 0)
    echo "[$(date -u +%H:%M:%SZ)] done ${arm} b${b} rc=${rc} lowmem_notices=${notices}"
    if [[ ${rc} -ne 0 ]]; then
      echo "[$(date -u +%H:%M:%SZ)] NONZERO EXIT; leaving artifacts for inspection"
    fi
  done
  echo "[$(date -u +%H:%M:%SZ)] block ${b} complete"
done
echo "[$(date -u +%H:%M:%SZ)] runner finished blocks ${FIRST}..${LAST}"
