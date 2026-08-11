#!/bin/bash
# Arm G rung 2: SPLIT=1 decode attribution for the norm-fused gate softplus.
#
# Why SPLIT=1 is mandatory here (N-DECODE-SPLIT-MANDATORY): with the shipped
# command-buffer batching policy, a single GPUPROF record covers many
# dispatches, so busy_sum double-counts co-resident kernels
# (busy_sum/busy_union = 1.1359 on this host) and `gate_sp` in particular is
# 96.4% nested inside a larger record. Per-kernel attribution of `rmsbfloat16`
# vs `gate_sp` is therefore only meaningful at SPLIT=1, where each record times
# exactly one dispatch.
#
# SPLIT=1 inflates the absolute wall by per-command-buffer overhead, so the
# wall printed here is NOT the shipped wall. It is used only to (a) attribute
# per-kernel busy and (b) count encoder dependency barriers. The shipped wall
# deltas come from research/nezuko_armg_ab.sh.
#
# The GPUPROF hook lives in Vendor/, which is NOT editable for submission, so
# this script applies the patch, builds an instrumented worker into a separate
# scratch path, and reverts Vendor/ before running anything.
#
# Usage: research/nezuko_armg_split_profile.sh <block> <arm> [<arm> ...]
set -u
cd "$(dirname "$0")/.."
REPO="${PWD}"

BLOCK="${1:?block name required}"
shift
OUT="research/armg-runs/${BLOCK}"
mkdir -p "${OUT}"
STEPS="${ARMG_PROF_STEPS:-40}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
SCRATCH=".build-prof"
WORKER="${REPO}/${SCRATCH}/release/mlxfast-runtime-worker"

cleanup() {
  git checkout -- Vendor 2>/dev/null || true
  git checkout -- Package.resolved 2>/dev/null || true
}
trap cleanup EXIT

echo "=== ${BLOCK}: vendor tree must be clean before patching"
if ! git diff --quiet -- Vendor; then
  echo "FATAL: Vendor/ already dirty; refusing to patch" >&2
  exit 2
fi

# APFS clone of the already-warm scratch path so only device.cpp recompiles.
if [ ! -d "${SCRATCH}" ]; then
  echo "=== cloning .build-worker -> ${SCRATCH} (APFS copy-on-write)"
  cp -Rc .build-worker "${SCRATCH}" || cp -R .build-worker "${SCRATCH}"
  # Precompiled clang modules record the absolute module-cache path they were
  # built under, so a cloned cache is rejected ("was compiled with module cache
  # path .../.build-worker/..."). Drop every cache dir; only .pcm files rebuild.
  rm -rf "${SCRATCH}/clang-module-cache"
  find "${SCRATCH}" -type d -name ModuleCache -prune -exec rm -rf {} + 2>/dev/null
  find "${SCRATCH}" -type d -name 'clang-module-cache' -prune -exec rm -rf {} + 2>/dev/null
fi

echo "=== applying ${PATCH}"
git apply --verbose "${PATCH}" || { echo "FATAL: patch failed" >&2; exit 3; }
grep -q DARKBLOOM_GPU_PROFILE_SPLIT \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
  || { echo "FATAL: hook not present after apply" >&2; exit 3; }

echo "=== adding intra-encoder barrier census"
python3 research/nezuko_r109_barrier_census_edit.py \
  || { echo "FATAL: barrier census edit failed" >&2; exit 3; }

echo "=== building instrumented worker into ${SCRATCH} t=$(date -u +%H:%M:%S)"
mkdir -p "${SCRATCH}/clang-module-cache"
CLANG_MODULE_CACHE_PATH="${REPO}/${SCRATCH}/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path "${SCRATCH}" --product mlxfast-runtime-worker \
    > "${OUT}/build.log" 2>&1
rc=$?
tail -5 "${OUT}/build.log"
if [ ${rc} -ne 0 ] || [ ! -x "${WORKER}" ]; then
  echo "FATAL: instrumented build failed rc=${rc}" >&2
  exit 4
fi
echo "=== reverting Vendor/ (instrumented binary is already linked)"
cleanup
git diff --stat -- Vendor Package.resolved

knob_for() {
  case "$1" in
    # Explicit since the shipped default moved from "1" to "0" after b5.
    C) echo "DARKBLOOM_NORM_FUSED_GATE_SP=1" ;;
    A) echo "DARKBLOOM_NORM_FUSED_GATE_SP=0" ;;
    W) echo "DARKBLOOM_NORM_FUSED_GATE_SP=2" ;;
    N) echo "DARKBLOOM_NORM_FUSED_GATE_SP=3" ;;
    S) echo "DARKBLOOM_NORM_FUSED_GATE_SP=4" ;;
    *) echo "BAD" ;;
  esac
}

# Pass 1: SPLIT=1 per-kernel busy attribution. Each GPUPROF record times
# exactly one dispatch, so `rmsbfloat16` and `gate_sp` stop being nested inside
# a larger co-resident record.
for arm in "$@"; do
  knob="$(knob_for "${arm}")"
  [ "${knob}" = "BAD" ] && { echo "unknown arm ${arm}" >&2; exit 2; }
  tag="split1-${arm}"
  echo "=== ${BLOCK} ${tag} knob='${knob}' t=$(date -u +%H:%M:%S)"
  # shellcheck disable=SC2086
  env ${knob} \
      DECODE_PROBE_WORKER="${WORKER}" \
      DARKBLOOM_GPU_PROFILE=1 \
      DARKBLOOM_GPU_PROFILE_SPLIT=1 \
      python3 research/decode_probe.py \
        --steps "${STEPS}" \
        --profile --profile-top 60 \
        --stderr "${OUT}/${tag}.err" \
      > "${OUT}/${tag}.prof" 2>&1
  echo "--- ${tag} rc=$?"
  sed -n '/^profile:/,$p' "${OUT}/${tag}.prof" | head -12
  echo "--- ${tag} barriers (expected ~0 at SPLIT=1): \
$(grep -c '^GPUBARRIER ' "${OUT}/${tag}.err" || true)"
  gzip -f "${OUT}/${tag}.err"
done

# Pass 2: SPLIT=0 barrier census under the shipped command-buffer batching
# policy, which is the only place the intra-encoder dependency graph is real.
# Timing here is contaminated by the per-barrier fprintf; only counts are used.
for arm in "$@"; do
  knob="$(knob_for "${arm}")"
  tag="split0-${arm}"
  echo "=== ${BLOCK} ${tag} knob='${knob}' t=$(date -u +%H:%M:%S)"
  # shellcheck disable=SC2086
  env ${knob} \
      DECODE_PROBE_WORKER="${WORKER}" \
      DARKBLOOM_GPU_PROFILE=1 \
      python3 research/decode_probe.py \
        --steps "${STEPS}" \
        --profile --profile-top 40 \
        --stderr "${OUT}/${tag}.err" \
      > "${OUT}/${tag}.prof" 2>&1
  echo "--- ${tag} rc=$?"
  sed -n '/^profile:/,$p' "${OUT}/${tag}.prof" | head -8
  echo "--- ${tag} barrier census (top blocked kernels, whole run):"
  grep '^GPUBARRIER ' "${OUT}/${tag}.err" \
    | sort | uniq -c | sort -rn | head -12
  echo "--- ${tag} total barriers: \
$(grep -c '^GPUBARRIER ' "${OUT}/${tag}.err" || true) over ${STEPS} steps"
  gzip -f "${OUT}/${tag}.err"
done
echo "=== ${BLOCK} done t=$(date -u +%H:%M:%S)"
