#!/usr/bin/env bash
# R102-B: run one 2-arm ABBA session from prebuilt factorial arm snapshots.
#
#   usage: bash /tmp/r102b-session.sh <session> <base_arm> <cand_arm> [REPS]
#   e.g.   bash /tmp/r102b-session.sh A arm00 arm10 7
#
# The canonical driver only knows the names base/cand, so each session gets a
# private SNAP dir whose base/ and cand/ are copies of the requested arms.
# REUSE_SNAP=1 means the driver never touches the working tree.
set -uo pipefail

ROOT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-tanjiro/workspace/target"
cd "${ROOT}" || exit 2

SESSION="$1"; BASE_ARM="$2"; CAND_ARM="$3"; REPS="${4:-7}"
ARMS="/tmp/r102b-arms"
SNAP="/tmp/r102b-sess${SESSION}-snap"
OUT="/tmp/r102b-sess${SESSION}"

for a in "${BASE_ARM}" "${CAND_ARM}"; do
  [ -x "${ARMS}/${a}/mlxfast-runtime-worker" ] || {
    echo "missing arm snapshot ${a}" >&2; exit 2; }
done

rm -rf "${SNAP}" "${OUT}" && mkdir -p "${SNAP}/base" "${SNAP}/cand" "${OUT}"
cp "${ARMS}/${BASE_ARM}"/* "${SNAP}/base/" || exit 3
cp "${ARMS}/${CAND_ARM}"/* "${SNAP}/cand/" || exit 3

{
  echo "session ${SESSION}: base=${BASE_ARM} cand=${CAND_ARM} REPS=${REPS}"
  echo "worker digests (rule 75, pre-timing):"
  shasum -a 256 "${SNAP}"/*/mlxfast-runtime-worker
  shasum -a 256 "${SNAP}"/*/mlx.metallib
} | tee "${OUT}/manifest.txt"

OUT="${OUT}" REPS="${REPS}" STEPS=200 SNAP="${SNAP}" REUSE_SNAP=1 \
  ORDER="base cand cand base" \
  bash research/maple_r85c_epilogue_ab.sh
rc=$?

echo "### driver exit=${rc}"
echo "worker digests (rule 75, post-timing):" | tee -a "${OUT}/manifest.txt"
shasum -a 256 "${SNAP}"/*/mlxfast-runtime-worker | tee -a "${OUT}/manifest.txt"
echo "### tree state after session ${SESSION}:"
git status --porcelain
git diff --name-only aba31ba9e461c8a4f7a0ba7086b417f0868fcad9 HEAD \
  -- Sources/ Vendor/ benchmark.json
exit "${rc}"
