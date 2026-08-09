#!/bin/bash
# R103-B fb3: stand up the THIRD revision e17bdeb1 (frontier receipt e08d759f's
# tree, i.e. base minus R3) and dump its MSL corpus, then take an A/A control by
# re-dumping the unchanged NEW tree a second time.
set -u

ROOT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-tanjiro/workspace/target"
MID_SHA=e17bdeb1
WT="${ROOT}/.mlxfast-private/r103b-mid"

cd "${ROOT}" || exit 3

echo "=== 1. worktree ==="
if [ ! -d "${WT}" ]; then
  git worktree add --detach "${WT}" "${MID_SHA}" || exit 4
fi
cd "${WT}" || exit 5
git --no-pager log --oneline -1

echo "=== 2. trace patch ==="
if ! git diff --quiet -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp; then
  echo "patch already applied"
else
  git apply --verbose "${ROOT}/research/r103b/scripts/trace.patch" || exit 6
fi
git --no-pager diff --stat

echo "=== 3. build worker ==="
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${WT}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
BRC=$?
git checkout -- Package.resolved 2>/dev/null || true
echo "build rc=${BRC}"
[ ${BRC} -eq 0 ] || exit 7

echo "=== 4. metallib ==="
SRC="${ROOT}/.build-worker/arm64-apple-macosx/release"
DST="${WT}/.build-worker/arm64-apple-macosx/release"
cp "${SRC}/mlx.metallib" "${SRC}/mlx.metallib.fingerprint" "${DST}/" || exit 8
ls -l "${DST}/mlxfast-runtime-worker" "${DST}/mlx.metallib"

echo "=== 5. staleness detector ==="
# R3 (#558) introduced DARKBLOOM_ROUTER_WEIGHT_PREFETCH. It must be ABSENT from
# the e17bdeb1 worker and PRESENT in the base worker; otherwise the build is stale.
for t in r103b-mid r103b-new r103b-old; do
  B="${ROOT}/.mlxfast-private/${t}/.build-worker/arm64-apple-macosx/release/mlxfast-runtime-worker"
  N=$(strings -a "${B}" 2>/dev/null | grep -c 'DARKBLOOM_ROUTER_WEIGHT_PREFETCH')
  echo "${t}: DARKBLOOM_ROUTER_WEIGHT_PREFETCH strings=${N} sha256=$(shasum -a 256 "${B}" | cut -c1-16) bytes=$(stat -f %z "${B}")"
done

echo "=== 6. trace mid ==="
bash "${ROOT}/research/r103b/scripts/run_trace.sh" r103b-mid mid

echo "=== 7. A/A control: re-dump NEW a second time ==="
bash "${ROOT}/research/r103b/scripts/run_trace.sh" r103b-new new_aa

echo BUILDMIDDONE
