#!/usr/bin/env bash
# Research-only (PR #457, R85-C rev2): counterbalanced ABBA timing for the
# re-ported float4 merge epilogue in the two decode fused-attention kernels.
#
# The arm here is a *source* difference, not an env flag, so the two arms are
# two prebuilt worker binaries snapshotted before any timing run:
#
#   base  Sources/MLXFastModel/LagunaRuntimeModel.swift at ${BASE_SHA}
#   cand  the same file at HEAD (float4 merge epilogue re-ported)
#
# The worker links every project module statically and resolves mlx.metallib
# through @loader_path, so a snapshot is exactly {executable, mlx.metallib}.
#
# ORDER="base cand cand base" gives two counterbalanced offset-0 duplexes per
# rep (base->cand and cand->base) and, read at --offset 1, cand/cand plus
# across-boundary base/base null duplexes for an in-session noise floor.
#
#   OUT=/tmp/maple-r85c-epi REPS=4 STEPS=200 \
#     bash research/maple_r85c_epilogue_ab.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-r85c-epi}"
REPS="${REPS:-4}"
STEPS="${STEPS:-200}"
BASE_SHA="${BASE_SHA:-7687c2e44e6975c181444ca8d3d151ee30480a72}"
ORDER="${ORDER:-base cand cand base}"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
SNAP="${SNAP:-/tmp/maple-r85c-snap}"
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

snapshot() {
  local name="$1" dir="${SNAP}/$1"
  rm -rf "${dir}" && mkdir -p "${dir}"
  cp .build-worker/release/mlxfast-runtime-worker "${dir}/" || return 1
  cp .build-worker/release/mlx.metallib "${dir}/" || return 1
  echo "### snapshot ${name}: $(shasum -a 256 "${dir}/mlxfast-runtime-worker" \
    | cut -c1-16)  $(stat -f%z "${dir}/mlxfast-runtime-worker") bytes"
}

cleanup() {
  echo "### restoring HEAD source"
  git checkout HEAD -- "${SRC}"
  if [ "${HOOK_PREAPPLIED}" = "1" ]; then
    echo "### GPU-profile hook was already applied on entry; leaving it"
  else
    echo "### reverting GPU-profile hook"
    git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
  fi
  build_worker "restore" || echo "WARNING: restore build failed"
}

if ! git diff --quiet -- "${SRC}"; then
  echo "refusing: ${SRC} is dirty; commit before timing" >&2
  exit 2
fi

if [ "${REUSE_SNAP:-0}" = "1" ] \
   && [ -x "${SNAP}/base/mlxfast-runtime-worker" ] \
   && [ -x "${SNAP}/cand/mlxfast-runtime-worker" ]; then
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

  build_worker "cand (HEAD)" || exit 4
  snapshot cand || exit 5
  git checkout "${BASE_SHA}" -- "${SRC}" || exit 6
  build_worker "base (${BASE_SHA:0:8})" || exit 7
  snapshot base || exit 8
  git checkout HEAD -- "${SRC}" || exit 9
fi

if cmp -s "${SNAP}/base/mlxfast-runtime-worker" \
          "${SNAP}/cand/mlxfast-runtime-worker"; then
  echo "refusing: base and cand executables are byte-identical" >&2
  exit 10
fi
shasum -a 256 "${SNAP}"/*/mlxfast-runtime-worker | tee "${OUT}/binaries.sha256"

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
