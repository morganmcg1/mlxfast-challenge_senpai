#!/bin/bash
# Research-only: certify the PR205 attention-merge-epilogue effect end to end on
# this M4 Pro host at a resolution the 128-step `--local-iterate` window cannot
# reach.
#
# Method (prescribed by the PR205 advisor note of 2026-08-07T05:56:39Z, adopted
# from PR204):
#   * `research/decode_probe.py`, 1200 decode steps per run, per-step
#     CLOCK_UPTIME_RAW spans, first 16 steps dropped as warmup.
#   * the RUN MEDIAN step time is the unit of replication, not the step.
#   * palindromic arm ordering A B B A A B B A A B B A, so any monotone drift in
#     host state cancels in the adjacent-pair differences.
#   * both binaries are built ONCE up front and then swapped as files, so no arm
#     carries a rebuild and the source tree is clean during every timed run.
#
# A = candidate (HEAD, float4 merge epilogue)      B = base (BASE_SHA)
set -u -o pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}" || exit 1

BASE_SHA="747d130be532383d3eabd190f54f8b1b2bc6f9fd"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
WORKER=".build-worker/release/mlxfast-runtime-worker"
OUT="/tmp/nezprobe"
STEPS="${STEPS:-1200}"
SEQ="${SEQ:-A B B A A B B A A B B A}"

mkdir -p "${OUT}"
echo "PROBE_START $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "REPO ${REPO}"
echo "HEAD $(git rev-parse HEAD)"
echo "BASE ${BASE_SHA}"
echo "STEPS ${STEPS}"
echo "SEQ ${SEQ}"

build_worker() {
  mkdir -p .build-worker/clang-module-cache
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
}

# ---------------------------------------------------------------- phase 1: build
cp "${SRC}" "${OUT}/src_head.swift" || exit 1
git show "${BASE_SHA}:${SRC}" > "${OUT}/src_base.swift" || exit 1
echo "SRC_MD5_HEAD $(md5 -q "${OUT}/src_head.swift")"
echo "SRC_MD5_BASE $(md5 -q "${OUT}/src_base.swift")"
if cmp -s "${OUT}/src_head.swift" "${OUT}/src_base.swift"; then
  echo "FATAL head and base sources are identical"; exit 1
fi

for arm in A B; do
  if [ "${arm}" = A ]; then cp "${OUT}/src_head.swift" "${SRC}"; else cp "${OUT}/src_base.swift" "${SRC}"; fi
  echo "BUILD_${arm}_START $(date -u +%H:%M:%SZ)"
  build_worker > "${OUT}/build_${arm}.log" 2>&1
  rc=$?
  echo "BUILD_${arm}_RC ${rc}"
  if [ ${rc} -ne 0 ]; then tail -30 "${OUT}/build_${arm}.log"; cp "${OUT}/src_head.swift" "${SRC}"; exit 1; fi
  cp "${WORKER}" "${OUT}/worker_${arm}"
  echo "BIN_MD5_${arm} $(md5 -q "${OUT}/worker_${arm}")"
done

cp "${OUT}/src_head.swift" "${SRC}"
git checkout -- Package.resolved 2>/dev/null
echo "WORKTREE_DIRTY_AFTER_BUILD $(git status --porcelain | wc -l | tr -d ' ')"
if cmp -s "${OUT}/worker_A" "${OUT}/worker_B"; then
  echo "FATAL the two worker binaries are byte-identical -- arms are inert"; exit 1
fi
echo "BINARIES_DIFFER 1"

# ------------------------------------------------------------- phase 2: palindrome
i=0
for arm in ${SEQ}; do
  i=$((i + 1))
  tag="$(printf '%02d' ${i})_${arm}"
  cp "${OUT}/worker_${arm}" "${WORKER}"
  echo "RUN_START ${tag} $(date -u +%H:%M:%SZ)"
  python3 research/decode_probe.py \
    --steps "${STEPS}" \
    --stderr "${OUT}/worker_${tag}.err" \
    --dump-steps "${OUT}/steps_${tag}.txt" \
    > "${OUT}/run_${tag}.log" 2>&1
  rc=$?
  echo "RUN_RC ${tag} ${rc}"
  grep -E "^(worker up|decode steps=|teacher-forced)" "${OUT}/run_${tag}.log" | sed "s/^/  ${tag} /"
  if [ ${rc} -ne 0 ]; then tail -20 "${OUT}/run_${tag}.log"; fi
done

# --------------------------------------------------------------- phase 3: analyse
echo "ANALYSE_START $(date -u +%H:%M:%SZ)"
SEQ="${SEQ}" STEPS="${STEPS}" python3 research/nezuko_decode_probe_stats.py "${OUT}"
echo "PROBE_DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)"
