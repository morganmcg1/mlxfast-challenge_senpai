#!/usr/bin/env bash
# R116-B step 1: prove DARKBLOOM_NVFP4_NIBBLE_SPLIT in {0,1,2} generates three
# genuinely distinct Metal sources, and that the source it changes is the one
# compiled into `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`.
#
# Why this is not optional.  Every kernel in the NVFP4 QMV family is registered
# under a FIXED string-literal name (LagunaRuntimeModel.swift:6907,7075,7084,
# 7099, ...) and MLX's `Device::get_library(name, builder)`
# (Vendor/mlx-swift/.../metal/device.cpp:770-786) calls the builder only on a
# name miss.  If two arms ever shared a process, arm 2 would silently execute
# arm 1's compiled library and the ABBA would return a fake null.  `library_map_`
# is a per-process std::unordered_map, not a disk cache, so one arm per process
# is sufficient -- but that has to be shown, not assumed.
#
# Method: patch an env-gated stderr dump into the tail of the
# `lagunaSharedSwiGLUQMVHeader` closure (:6764-6911) and print the exact string
# MLX is handed.  The dump fires from the lazy global's initializer, so it also
# proves the header was actually materialised in a real decode run rather than
# reconstructed by this script.  The patch is reverted on every exit path.
#
#   research/maple-tanjiro-r110/nibble-split-reachability.sh [OUT_DIR] [STEPS]
set -u
cd "$(dirname "$0")/../.."
ROOT="${PWD}"
PATCH="research/maple-tanjiro-r110/qmv-header-dump.patch"

OUT="${1:-/tmp/r116b-reach}"
STEPS="${2:-8}"
mkdir -p "${OUT}"

revert() {
  cd "${ROOT}" || return
  git apply -R "${PATCH}" 2>/dev/null
  git checkout -- Sources/MLXFastModel/LagunaRuntimeModel.swift 2>/dev/null
  git checkout -- Package.resolved 2>/dev/null
  echo "=== patch reverted t=$(date -u +%H:%M:%S)"
  git status --short
}
trap revert EXIT

echo "=== apply dump patch t=$(date -u +%H:%M:%S)"
git apply "${PATCH}" || { echo "patch failed"; exit 2; }

echo "=== build instrumented worker t=$(date -u +%H:%M:%S)"
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    > "${OUT}/build.log" 2>&1
rc=$?
git checkout -- Package.resolved 2>/dev/null
[ ${rc} -ne 0 ] && { echo "build failed rc=${rc}"; tail -40 "${OUT}/build.log"; exit 3; }
echo "=== build ok t=$(date -u +%H:%M:%S)"

for split in 0 1 2; do
  echo "=== dump split=${split} t=$(date -u +%H:%M:%S)"
  err="${OUT}/split${split}.err"
  DARKBLOOM_DUMP_QMV_HEADER=1 DARKBLOOM_NVFP4_NIBBLE_SPLIT="${split}" \
    python3 research/decode_probe.py --steps "${STEPS}" \
      --stderr "${err}" > "${OUT}/split${split}.log" 2>&1
  rc=$?
  [ ${rc} -ne 0 ] && { echo "run rc=${rc}"; tail -20 "${OUT}/split${split}.log"; }
  awk '/^===QMVHEADER_BEGIN/{f=1} f{print} /^===QMVHEADER_END/{f=0}' \
    "${err}" > "${OUT}/header_split${split}.metal"
  n=$(wc -l < "${OUT}/header_split${split}.metal" | tr -d ' ')
  echo "split=${split} header_lines=${n}"
  [ "${n}" -lt 10 ] && { echo "EMPTY DUMP -- flag never reached the header"; }
done

echo
echo "=== sha256 of the exact string handed to MLX ==="
shasum -a 256 "${OUT}"/header_split*.metal

echo
echo "=== pairwise distinctness ==="
for pair in "0 1" "0 2" "1 2"; do
  set -- ${pair}
  d=$(diff "${OUT}/header_split$1.metal" "${OUT}/header_split$2.metal" | grep -c '^[<>]')
  echo "split$1 vs split$2 : ${d} differing lines"
done

echo
echo "=== extract block per arm (the only intended difference) ==="
for split in 0 1 2; do
  echo "--- split=${split}"
  sed -n '/const uint c = codes.x/,/const float2 v04/p' \
    "${OUT}/header_split${split}.metal" | sed '$d'
done

echo
echo "=== marker lines (confirms the flag was parsed in-process) ==="
grep -h '^===QMVHEADER_BEGIN' "${OUT}"/header_split*.metal

echo "=== done t=$(date -u +%H:%M:%S)"
