#!/usr/bin/env bash
# R119-B full measurement campaign for the grid-appended shared+routed gate/up
# QMV, ranked on the end-to-end SPLIT=0 decode wall.
#
# Three phases, all from one binary with no GPU-profile hook applied:
#   1. ABBA order  CFFC x BLOCKS   -> n = 2*BLOCKS per arm
#   2. BAAB order  FCCF x BLOCKS   -> mirrored, reported separately
#   3. negative control CNNC x NC_BLOCKS, where N is labelled like the
#      candidate but runs byte-identical baseline work in the same block
#      structure, so any "effect" it shows is pure instrument bias.
#
# Each phase appends raw per-step samples as it goes, so a late failure still
# leaves the earlier phases analysable.
#
# Research-only; not on editablePaths.
#   OUT=/tmp/r119b BLOCKS=9 NC_BLOCKS=4 STEPS=256 bash research/edward_r119b_campaign.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/r119b}"
STEPS="${STEPS:-256}"
BLOCKS="${BLOCKS:-9}"
NC_BLOCKS="${NC_BLOCKS:-4}"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty (GPU-profile hook still applied?)" >&2
  exit 2
fi
echo "### HEAD: $(git rev-parse HEAD)"

echo "### rebuilding the clean scored worker (no profile hook)"
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
}

phase abba "$(rep CFFC "${BLOCKS}")" 1
phase baab "$(rep FCCF "${BLOCKS}")" 0
phase nc   "$(rep CNNC "${NC_BLOCKS}")" 0

echo "##################### statistics #####################"
echo "=== ABBA order (C vs F) ==="
python3 research/edward_r119b_stats.py "${OUT}/abba_raw.csv"
echo "=== BAAB order (C vs F) ==="
python3 research/edward_r119b_stats.py "${OUT}/baab_raw.csv"
echo "=== both orders pooled (C vs F) ==="
python3 research/edward_r119b_stats.py --pool "${OUT}/abba_raw.csv" "${OUT}/baab_raw.csv"
echo "=== negative control (C vs N, both gate=0) ==="
python3 research/edward_r119b_stats.py --candidate N "${OUT}/nc_raw.csv"
