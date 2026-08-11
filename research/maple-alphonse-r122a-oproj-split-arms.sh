#!/bin/bash
# R122-A: does nezuko's o_proj `results_per_simdgroup` 4 -> 2 win show up as
# per-kernel GPU busy (throughput), or as gap / overlap absorption?
#
#   research/maple-alphonse-r122a-oproj-split-arms.sh [OUT] [STEPS] [SEQ1] [SEQ2]
#
# SEQ1 runs under SPLIT=1 (one dispatch per command buffer, so a busy record
# names a kernel) at the host's automatic startup memory profile.
# SEQ2 runs under SPLIT=0 (real MLX batching, so the inter-command-buffer gap
# exists) at the ranked `full` startup memory profile.
# Letters: C = rps 4 (pre-merge), R = rps 2 (shipped default), O = rps 1.
#
# One binary serves every cell; the geometry is a process-start env read, so
# no cell can be confounded by a rebuild. The GPUPROF hook is research-only
# instrumentation held in a patch file, applied here and reverted on every
# exit path.
set -u
cd "$(dirname "$0")/.."

OUT="${1:-/tmp/r122a}"
STEPS="${2:-200}"
SEQ1="${3:-CRRCRCCRCR}"
SEQ2="${4:-CRRC}"
PATCH="research/pr91-gpuprof-hook.patch"
TOUCHED="Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h"

mkdir -p "${OUT}"

revert() {
  # shellcheck disable=SC2086
  git checkout -- ${TOUCHED}
  echo "=== reverted ${PATCH}"
  # shellcheck disable=SC2086
  git status --porcelain -- ${TOUCHED}
}
trap revert EXIT

echo "=== applying ${PATCH} t=$(date -u +%H:%M:%S)"
git apply "${PATCH}" || exit 2

echo "=== building instrumented worker t=$(date -u +%H:%M:%S)"
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    > "${OUT}/build.log" 2>&1
rc=$?
git checkout -- Package.resolved 2>/dev/null
if [ ${rc} -ne 0 ]; then
  echo "build failed rc=${rc}"
  tail -40 "${OUT}/build.log"
  exit 3
fi
echo "=== build ok t=$(date -u +%H:%M:%S)"

cell() {
  idx="$1"; letter="$2"; split="$3"; profile="$4"
  case "${letter}" in
    C) rps=4 ;;
    R) rps=2 ;;
    O) rps=1 ;;
    *) echo "unknown arm ${letter}"; return 9 ;;
  esac
  tag=$(printf "%02d-%s-s%s-%s" "${idx}" "${letter}" "${split}" "${profile}")
  echo "=== cell ${tag} rps=${rps} t=$(date -u +%H:%M:%S)"
  if [ "${profile}" = "full" ]; then
    env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="${split}" \
      DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP="${rps}" \
      DARKBLOOM_REPORT_CB_ENV=1 DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
      python3 research/decode_probe.py --steps "${STEPS}" --profile \
        --profile-top 60 --stderr "${OUT}/${tag}.err" \
      > "${OUT}/${tag}.log" 2>&1
  else
    env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="${split}" \
      DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP="${rps}" \
      DARKBLOOM_REPORT_CB_ENV=1 \
      python3 research/decode_probe.py --steps "${STEPS}" --profile \
        --profile-top 60 --stderr "${OUT}/${tag}.err" \
      > "${OUT}/${tag}.log" 2>&1
  fi
  crc=$?
  echo "--- ${tag} rc=${crc} t=$(date -u +%H:%M:%S)"
  grep -m1 'cb-env' "${OUT}/${tag}.err" || echo "!!! ${tag}: NO cb-env READBACK -- VOID"
  grep -E 'per steady step|divergences|decode steps=' "${OUT}/${tag}.log"
  grep -E 'oproj_act_h(64|48)' "${OUT}/${tag}.log"
  gzip -f "${OUT}/${tag}.err"
}

i=0
for letter in $(echo "${SEQ1}" | fold -w1); do
  i=$((i + 1))
  cell "${i}" "${letter}" 1 auto
done
for letter in $(echo "${SEQ2}" | fold -w1); do
  i=$((i + 1))
  cell "${i}" "${letter}" 0 full
done

echo "=== done t=$(date -u +%H:%M:%S)"
