#!/usr/bin/env bash
# R102-B: build the four 2x2 factorial arms as relocatable worker snapshots.
#
#   arm00  neither restoration      arm10  R1 (float4 merge epilogue) only
#   arm01  R2 (4-deep ring) only    arm11  both == HEAD
#
# Source files come from /tmp/r102b-static/armXX.swift (verified sha256).
# The GPU-profile hook is applied so the snapshots emit per-kernel GPUPROF.
# The tree is restored by the EXIT trap; verify the scope diff afterwards.
set -uo pipefail

ROOT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-tanjiro/workspace/target"
cd "${ROOT}" || exit 2

SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
ARMSRC="/tmp/r102b-static"
SNAP="${SNAP:-/tmp/r102b-arms}"
HOOK_PREAPPLIED=0

expect_sha() {
  case "$1" in
    arm00) echo c9074bdbe90879e1cfdae4af0c1f57ae5921dfee712ce9102858915d7108cdc0 ;;
    arm10) echo 22b2db96bda47d921687cebb0b8f25ddf87a2ddd2b7b2feac32a92ef2618a02a ;;
    arm01) echo a7c76a9aa2fe06be66a56220e18db1e75259f81abf9572e82136b3a3f3a3835b ;;
    arm11) echo 5e9192b91591f82d53d52a6f017f4446fa5eddbe4b84d81cfa1966ff1ef68018 ;;
  esac
}

if ! git diff --quiet -- "${SRC}"; then
  echo "refusing: ${SRC} is dirty" >&2; exit 2
fi
for a in arm00 arm10 arm01 arm11; do
  got=$(shasum -a 256 "${ARMSRC}/${a}.swift" | cut -d' ' -f1)
  if [ "${got}" != "$(expect_sha "${a}")" ]; then
    echo "refusing: ${a}.swift sha mismatch: ${got}" >&2; exit 2
  fi
done
echo "### all four arm sources verified by sha256"

build_worker() {
  echo "### building worker ($1)"
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null || true
  return "${rc}"
}

cleanup() {
  echo "### restoring HEAD source"
  git checkout HEAD -- "${SRC}"
  if [ "${HOOK_PREAPPLIED}" = "1" ]; then
    echo "### hook was pre-applied on entry; leaving it"
  else
    echo "### reverting GPU-profile hook"
    git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
  fi
  echo "### post-restore scope diff (must be empty):"
  git diff --name-only aba31ba9e461c8a4f7a0ba7086b417f0868fcad9 HEAD \
    -- Sources/ Vendor/ benchmark.json
  git status --porcelain
}

if git apply --reverse --check "${PATCH}" 2>/dev/null; then
  HOOK_PREAPPLIED=1
  echo "### GPU-profile hook already present; reusing it"
elif git diff --quiet -- Vendor; then
  git apply "${PATCH}" || exit 3
else
  echo "refusing: Vendor tree is dirty" >&2; exit 2
fi
trap cleanup EXIT

for a in arm00 arm10 arm01 arm11; do
  cp "${ARMSRC}/${a}.swift" "${SRC}" || exit 4
  build_worker "${a}" || exit 5
  d="${SNAP}/${a}"
  rm -rf "${d}" && mkdir -p "${d}"
  cp .build-worker/release/mlxfast-runtime-worker "${d}/" || exit 6
  cp .build-worker/release/mlx.metallib "${d}/" || exit 6
  echo "### snapshot ${a}: $(shasum -a 256 "${d}/mlxfast-runtime-worker" \
    | cut -c1-16)  $(stat -f%z "${d}/mlxfast-runtime-worker") bytes"
done

echo "########## arm worker digests (rule 75) ##########"
shasum -a 256 "${SNAP}"/arm*/mlxfast-runtime-worker | tee "${SNAP}/workers.sha256"
shasum -a 256 "${SNAP}"/arm*/mlx.metallib | tee "${SNAP}/metallibs.sha256"

fail=0
for pair in "arm00 arm10" "arm00 arm01" "arm00 arm11" "arm10 arm11" "arm01 arm11"; do
  set -- ${pair}
  if cmp -s "${SNAP}/$1/mlxfast-runtime-worker" "${SNAP}/$2/mlxfast-runtime-worker"; then
    echo "PROBLEM: $1 and $2 workers are byte-identical"; fail=1
  fi
done
echo "########## distinctness fail=${fail} ##########"
