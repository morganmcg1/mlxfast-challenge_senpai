#!/usr/bin/env bash
# Research-only (PR #558, R100-C): in-situ per-kernel ABBA census over the
# restored DARKBLOOM_ROUTER_WEIGHT_PREFETCH arms.
#
#   bash research/maple-nezuko-r100c-census.sh OUTDIR [REPS] [STEPS] [SPLIT]
#
# Slots (research/maple_r89_insitu.py ARM_LABEL):
#   0   pf0  unhoisted baseline
#   0b  pf0  byte-identical repeat -> the rig's own null control and floor
#   1   pf1  hoisted candidate (shipped default)
#   5   pf1c character-identical peel emitted BELOW the normalize barrier
#
# The census needs per-dispatch kernel attribution, which lives in the
# research-only GPU-profile hook, not in the submitted tree. This script
# applies that Vendor hook, builds the probe worker with it, runs the sweep and
# reverts the hook on every exit path. The submitted surface is unchanged: the
# recorded before/after Sources+Vendor digests must match.
#
# SPLIT=1 gives per-kernel attribution and inflates absolute GPU time; it is
# only ever an arm-vs-arm relative estimator (rule 43), never an end-to-end
# magnitude.
set -uo pipefail

OUT="${1:?usage: OUTDIR [REPS] [STEPS] [SPLIT]}"
REPS="${2:-8}"
STEPS="${3:-300}"
SPLIT="${4:-1}"
SLOTS="${R100C_SLOTS:-0,0b,1,5}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
WORKER="${PWD}/.build-worker/release/mlxfast-runtime-worker"
HOOK_APPLIED=0

mkdir -p "${OUT}"

tree_digest() {
  find Sources Vendor -type f -print0 | sort -z | xargs -0 shasum -a 256 \
    | shasum -a 256 | awk '{print $1}'
}

DIGEST_BEFORE="$(tree_digest)"
{
  printf 'head=%s\n' "$(git rev-parse HEAD)"
  printf 'digest_before=%s\n' "${DIGEST_BEFORE}"
  printf 'slots=%s reps=%s steps=%s split=%s\n' \
    "${SLOTS}" "${REPS}" "${STEPS}" "${SPLIT}"
} | tee "${OUT}/provenance.txt"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor dirty; commit before timing" >&2
  exit 2
fi

build_worker() {
  echo "### building probe worker ($1)"
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null || true
  return "${rc}"
}

cleanup() {
  if [ "${HOOK_APPLIED}" = "1" ]; then
    echo "### reverting GPU-profile hook"
    git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
    HOOK_APPLIED=0
  fi
  local after
  after="$(tree_digest)"
  printf 'digest_after=%s\n' "${after}" | tee -a "${OUT}/provenance.txt"
  if [ "${after}" != "${DIGEST_BEFORE}" ]; then
    echo "WARNING: Sources+Vendor digest did not return to its pre-run value" \
      | tee -a "${OUT}/provenance.txt"
  fi
}
trap cleanup EXIT

git apply "${PATCH}" || exit 3
HOOK_APPLIED=1
build_worker "HEAD + gpuprof hook" || exit 4
shasum -a 256 "${WORKER}" | tee "${OUT}/worker.sha256"

R89_SLOTS="${SLOTS}" python3 research/maple_r89_insitu.py \
  "${OUT}" "${REPS}" "${STEPS}" "${SPLIT}" 2>&1 | tee "${OUT}/sweep.log"
rc=${PIPESTATUS[0]}
echo "census rc=${rc}"
exit "${rc}"
