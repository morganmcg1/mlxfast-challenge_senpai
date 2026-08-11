#!/usr/bin/env bash
# R119-B rev2: repeat the SPLIT=0 paired wall A/B under the FULL startup memory
# profile, so the auto (low-memory) cells measured on this 48 GiB host can be
# read beside a cell whose MLX command-buffer structure matches the ranked M5.
#
# The low-memory profile pins MLX_MAX_OPS_PER_BUFFER=64 / MLX_MAX_MB_PER_BUFFER=128
# and leaves MLX_BFS_MAX_WIDTH at the MLX default, which is exactly the axis a
# dispatch-count change is expected to move. Every worker prints the three
# variables it can actually see (DARKBLOOM_ENV_READBACK=1); the cell is void
# unless they read 200 / 200 / 50.
#
# Research-only; not on editablePaths.
#   OUT=/tmp/r119b-full BLOCKS=9 STEPS=256 bash research/edward_r119b_fullprofile.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/r119b-full}"
STEPS="${STEPS:-256}"
BLOCKS="${BLOCKS:-9}"
mkdir -p "${OUT}"

export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
export DARKBLOOM_ENV_READBACK=1

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty" >&2
  exit 2
fi
echo "### HEAD: $(git rev-parse HEAD)"
echo "### profile=${DARKBLOOM_STARTUP_MEMORY_PROFILE} blocks=${BLOCKS} steps=${STEPS}"

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
[ "${rc}" -eq 0 ] || exit 3

rep() { local u="$1" k="$2" s=""; for ((i=0;i<k;i++)); do s+="${u}"; done; printf '%s' "${s}"; }

phase() {
  local tag="$1" order="$2" warm="$3"
  echo "##################### phase ${tag}: ${order} #####################"
  OUT="${OUT}" TAG="${tag}" ORDER="${order}" STEPS="${STEPS}" WARMUP="${warm}" \
    bash research/edward_r119b_abba.sh
  echo "### phase ${tag} exit=$?"
  echo "### env readback witnesses for ${tag}:"
  grep -h ENVREADBACK "${OUT}/${tag}"_*.err 2>/dev/null | sort | uniq -c
  echo "### low-memory notices for ${tag} (must be zero):"
  grep -hc 'low-memory startup profile active' "${OUT}/${tag}"_*.err 2>/dev/null \
    | awk '{s+=$1} END {print s+0}'
}

phase abba "$(rep CFFC "${BLOCKS}")" 1
phase baab "$(rep FCCF "${BLOCKS}")" 0

echo "##################### statistics (FULL profile) #####################"
echo "=== ABBA order (C vs F) ==="
python3 research/edward_r119b_stats.py "${OUT}/abba_raw.csv"
echo "=== BAAB order (C vs F) ==="
python3 research/edward_r119b_stats.py "${OUT}/baab_raw.csv"
echo "=== both orders pooled (C vs F) ==="
python3 research/edward_r119b_stats.py --pool "${OUT}/abba_raw.csv" "${OUT}/baab_raw.csv"
echo "FULLPROFILE_CAMPAIGN_DONE"
