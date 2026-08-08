#!/usr/bin/env bash
# Research-only (PR #456, R85-B rev2): counterbalanced ABBA timing for the
# LagunaRuntimeModel.swift -> LagunaRuntimeLayers.swift file split.
#
# Adapted from research/maple_r85c_epilogue_ab.sh (PR #457). Two differences
# matter:
#
#  1. The arm is a *two-file* difference. The base arm restores the pre-split
#     LagunaRuntimeModel.swift AND removes LagunaRuntimeLayers.swift, so the
#     upstream driver's single-${SRC} checkout is not sufficient.
#
#  2. A third arm, `cand2`, is built from source byte-identical to `cand`.
#     Its only difference from `cand` is that it is an independent trip
#     through the compiler and linker. The cand/cand2 contrast therefore
#     measures the *build lottery* -- the run-to-run spread this rig reports
#     when the true source-attributable effect is exactly zero by
#     construction. #457 found 11.1 us/step (42%) of a kernel-local saving
#     given back on kernels with zero source changes; a neutrality claim that
#     cannot bound that band is not a measurement.
#
# ORDER="base cand cand2 cand2 cand base" with REPS=4 yields, over 24 runs:
#
#   --offset 0 --arms base cand    n=8 counterbalanced   (the effect)
#   --offset 1 --arms cand cand2   n=8 counterbalanced   (build lottery)
#   --offset 0 --arms cand2 cand2  n=4 null duplex
#   --offset 1 --arms base base    n=4 null duplex (across rep boundary)
#
#   OUT=/tmp/maple-r85b-split REPS=4 STEPS=200 \
#     BASE_SHA=3217f111142346e004f41fae611a8bede172a659 \
#     bash research/maple_r85b_split_ab.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-r85b-split}"
REPS="${REPS:-4}"
STEPS="${STEPS:-200}"
BASE_SHA="${BASE_SHA:-3217f111142346e004f41fae611a8bede172a659}"
ORDER="${ORDER:-base cand cand2 cand2 cand base}"
SRC_MODEL="Sources/MLXFastModel/LagunaRuntimeModel.swift"
SRC_LAYERS="Sources/MLXFastModel/LagunaRuntimeLayers.swift"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
SNAP="${SNAP:-/tmp/maple-r85b-snap}"
OBJDIR=".build-worker/release/MLXFastModel.build"
HOOK_PREAPPLIED=0

mkdir -p "${OUT}"

build_worker() {
  echo "### building worker ($1)"
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null || true
  return "${rc}"
}

# SwiftPM leaves the .o of a deleted source behind; an emitted-code dump that
# globs the object directory would then attribute a removed file's code to the
# arm that does not contain it.
prune_stale_objects() {
  local obj base
  for obj in "${OBJDIR}"/*.o; do
    [ -e "${obj}" ] || continue
    base=$(basename "${obj}" .o)
    if [ ! -f "Sources/MLXFastModel/${base}" ]; then
      echo "### pruning stale object ${base}.o"
      rm -f "${obj}"
    fi
  done
}

snapshot() {
  local name="$1" dir="${SNAP}/$1"
  rm -rf "${dir}" && mkdir -p "${dir}"
  cp .build-worker/release/mlxfast-runtime-worker "${dir}/" || return 1
  cp .build-worker/release/mlx.metallib "${dir}/" || return 1
  prune_stale_objects
  python3 research/fern_emit_compare.py dump "${OBJDIR}" \
    "${OUT}/emit-${name}.json" || return 1
  ls -1 "${OBJDIR}"/*.o | xargs -n1 basename > "${OUT}/objects-${name}.txt"
  echo "### snapshot ${name}: $(shasum -a 256 "${dir}/mlxfast-runtime-worker" \
    | cut -c1-16)  $(stat -f%z "${dir}/mlxfast-runtime-worker") bytes"
}

restore_head_sources() {
  git checkout HEAD -- "${SRC_MODEL}" "${SRC_LAYERS}"
}

cleanup() {
  echo "### restoring HEAD source"
  restore_head_sources
  if [ "${HOOK_PREAPPLIED}" = "1" ]; then
    echo "### GPU-profile hook was already applied on entry; leaving it"
  else
    echo "### reverting GPU-profile hook"
    git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
  fi
  build_worker "restore" || echo "WARNING: restore build failed"
}

if ! git diff --quiet -- "${SRC_MODEL}" "${SRC_LAYERS}"; then
  echo "refusing: split sources are dirty; commit before timing" >&2
  exit 2
fi

if [ "${REUSE_SNAP:-0}" = "1" ] \
   && [ -x "${SNAP}/base/mlxfast-runtime-worker" ] \
   && [ -x "${SNAP}/cand/mlxfast-runtime-worker" ] \
   && [ -x "${SNAP}/cand2/mlxfast-runtime-worker" ]; then
  echo "### reusing existing snapshots in ${SNAP}"
else
  if git apply --reverse --check "${PATCH}" 2>/dev/null; then
    HOOK_PREAPPLIED=1
    echo "### GPU-profile hook already present; reusing it"
  elif git diff --quiet -- Vendor; then
    git apply "${PATCH}" || exit 3
  else
    echo "refusing: Vendor tree is dirty; revert before applying the hook" >&2
    exit 2
  fi
  trap cleanup EXIT

  build_worker "cand (HEAD, split)" || exit 4
  snapshot cand || exit 5

  git checkout "${BASE_SHA}" -- "${SRC_MODEL}" || exit 6
  rm -f "${SRC_LAYERS}" || exit 6
  build_worker "base (${BASE_SHA:0:8}, single file)" || exit 7
  snapshot base || exit 8

  # cand2 is byte-identical source to cand; only the build differs.
  restore_head_sources || exit 9
  build_worker "cand2 (HEAD, split, independent re-roll)" || exit 4
  snapshot cand2 || exit 5
fi

if cmp -s "${SNAP}/base/mlxfast-runtime-worker" \
          "${SNAP}/cand/mlxfast-runtime-worker"; then
  echo "refusing: base and cand executables are byte-identical" >&2
  exit 10
fi
if cmp -s "${SNAP}/cand/mlxfast-runtime-worker" \
          "${SNAP}/cand2/mlxfast-runtime-worker"; then
  echo "### NOTE: cand and cand2 executables are byte-identical;"
  echo "### the lottery arm degenerates to a pure session-noise null."
else
  echo "### cand and cand2 differ: the build lottery is live and measurable."
fi
shasum -a 256 "${SNAP}"/*/mlxfast-runtime-worker | tee "${OUT}/binaries.sha256"
for a in base cand cand2; do
  echo "${a} size=$(stat -f%z "${SNAP}/${a}/mlxfast-runtime-worker")"
done | tee "${OUT}/binary-sizes.txt"

run_slot() {
  local tag="$1" arm="$2"
  DECODE_PROBE_WORKER="${SNAP}/${arm}/mlxfast-runtime-worker" \
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      --profile-top 8 --stderr "${OUT}/${tag}.err" \
      --dump-steps "${OUT}/${tag}.steps" \
      --dump-tokens "${OUT}/${tag}.tokens" \
      >"${OUT}/${tag}.log" 2>&1
}

echo "########## unscored warm-up run ##########"
run_slot warmup base
echo "warm-up exit=$?"

slots=0
for arm in ${ORDER}; do slots=$((slots + 1)); done
echo "########## ${REPS} reps x ${slots} slots = $((REPS * slots)) runs ##########"

idx=0
for rep in $(seq 1 "${REPS}"); do
  for arm in ${ORDER}; do
    idx=$((idx + 1))
    tag=$(printf "%02d-rep%s-%s" "${idx}" "${rep}" "${arm}")
    echo "=== ${tag} ==="
    run_slot "${tag}" "${arm}"
    rc=$?
    grep -E "^decode steps=|^teacher-forced|^prefill" "${OUT}/${tag}.log" \
      || echo "  (no summary; exit=${rc})"
  done
done

echo "########## token identity across arms ##########"
cksum "${OUT}"/[0-9]*.tokens | awk '{print $1, $3}'
echo "########## done ##########"
