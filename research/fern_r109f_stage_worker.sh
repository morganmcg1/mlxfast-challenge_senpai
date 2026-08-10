#!/usr/bin/env bash
# R109-F integration: stage a runtime worker for one labelled git state.
#
# benchmark.sh resolves the participant binary from
# MLXFAST_RUNTIME_WORKER_EXECUTABLE (benchmark.sh:212) and mlx.metallib from
# *that binary's directory* (benchmark.sh:213). So a labelled directory holding
# a worker plus its own metallib is a complete, self-contained arm: paired
# timing can then interleave arms inside one session with no rebuild between
# slots, which is the only way to get n>=4 usable pairs per arm for five arms
# inside the round.
#
# The metallib is COPIED, not symlinked. An arm that edits an AOT kernel source
# (RoPE, RMSNorm, SDPA vector, arg_reduce, or any Vendor/mlx-swift .metal or
# mlx-generated twin) produces a different metallib, and a symlink into the
# live .build-worker tree would silently give every staged arm the newest one.
# The three resource bundles are inputs the challenge never edits, so those are
# symlinked to save ~100 MB per label.
#
# Usage: LABEL=<name> research/fern_r109f_stage_worker.sh
# Env:   ROOT=<dir>  staging root (default /tmp/fern-r109f/workers)
set -uo pipefail
cd "$(dirname "$0")/.."

LABEL="${LABEL:?LABEL is required, e.g. LABEL=base}"
ROOT="${ROOT:-/tmp/fern-r109f/workers}"
DEST_DIR="${ROOT}/${LABEL}"
BUILT=.build-worker/release
BUNDLES="mlx-swift-lm_MLXLMCommon.bundle swift-crypto_Crypto.bundle swift-transformers_Hub.bundle"

echo "=== stage worker label=${LABEL} head=$(git rev-parse --short HEAD) dirty=$(git status --porcelain -- Sources Vendor | wc -l | tr -d ' ') start $(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p .build/clang-module-cache .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
if [ "$rc" -ne 0 ]; then
  echo "FATAL: worker build failed for label=${LABEL}" >&2
  exit 1
fi

mkdir -p "${DEST_DIR}"
cp "${BUILT}/mlxfast-runtime-worker" "${DEST_DIR}/mlxfast-runtime-worker"
for f in mlx.metallib mlx.metallib.fingerprint; do
  if [ -e "${BUILT}/${f}" ]; then
    cp "${BUILT}/${f}" "${DEST_DIR}/${f}"
  else
    echo "FATAL: ${BUILT}/${f} missing; run tools/build-mlx-metallib.sh" >&2
    exit 1
  fi
done
for b in ${BUNDLES}; do
  ln -sfn "${PWD}/${BUILT}/${b}" "${DEST_DIR}/${b}"
done

# Provenance: the binary hash is the only thing that proves two labels are
# actually different code, and the metallib hash the only thing that proves a
# kernel-source arm rebuilt what it claimed to.
{
  echo "label=${LABEL}"
  echo "staged_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_head=$(git rev-parse HEAD)"
  echo "git_describe=$(git rev-parse --abbrev-ref HEAD)"
  echo "worker_sha256=$(shasum -a 256 "${DEST_DIR}/mlxfast-runtime-worker" | awk '{print $1}')"
  echo "metallib_sha256=$(shasum -a 256 "${DEST_DIR}/mlx.metallib" | awk '{print $1}')"
  git status --porcelain -- Sources Vendor | sed 's/^/dirty:/'
} > "${DEST_DIR}/PROVENANCE.txt"

cat "${DEST_DIR}/PROVENANCE.txt"
echo "=== staged -> ${DEST_DIR}"
