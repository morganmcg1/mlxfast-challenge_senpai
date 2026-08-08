#!/usr/bin/env bash
# Research-only (PR #473, R88-A): two-regime counterbalanced ABBA for the
# R85-C float4 merge epilogue (PR #457).
#
# PR #457 reported every number -- the touched-kernel savings (-26.53 us/step),
# the untouched-kernel give-back (+8.14 on laguna_gate_sp_h64_v1) and the net
# (-15.43) -- from ONE instrument: total steady GPU busy under
# DARKBLOOM_GPU_PROFILE_SPLIT=1, which puts every dispatch in its own command
# buffer. Sum(per-kernel) is then identically the total by construction, so the
# "give-back" is a measured increase in other kernels' own *serialised* busy
# time, not an end-to-end wall effect and not overlap absorbed elsewhere.
#
# The one thing that separates a real give-back from an instrument artefact is
# running the same two binaries at both dispatch regimes in one session:
#
#   s1   DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1
#        406 command buffers/step, one dispatch each: replicates PR #457 and
#        keeps per-kernel attribution.
#   nat  DARKBLOOM_GPU_PROFILE=1, SPLIT unset
#        ~45 command buffers/step, MLX's shipped concurrent dispatch: total
#        busy is the honest cost proxy, plus wall / sum / union / gap.
#
# Primary readout: (nat total-busy delta) / (s1 touched-kernel sum). ~1.0 means
# the give-back is an artefact of the SPLIT=1 instrument; ~0.58 means it
# survives in the shipped regime.
#
# The two arms are two prebuilt worker binaries snapshotted before any timing
# run (the arm is a source difference, not an env flag):
#
#   base  Sources/MLXFastModel/LagunaRuntimeModel.swift at ${BASE_SHA}
#         (417f42c4 = first parent of the PR #457 merge, i.e. pre-epilogue)
#   cand  the same file at HEAD (float4 merge epilogue present)
#
# ORDER="base cand cand base" gives two counterbalanced offset-0 duplexes per
# rep per regime and, at --offset 1, same-arm null duplexes for the in-session
# noise floor. The regime block order flips on even reps so regime is
# counterbalanced against session drift as well.
#
#   OUT=/tmp/maple-r88a REPS=4 STEPS=200 \
#     bash research/maple_r88a_two_regime_ab.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-r88a}"
REPS="${REPS:-4}"
STEPS="${STEPS:-200}"
BASE_SHA="${BASE_SHA:-417f42c4167344afd2156b6f5d8ab76e2bf419f3}"
ORDER="${ORDER:-base cand cand base}"
REGIMES="${REGIMES:-s1 nat}"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
SNAP="${SNAP:-/tmp/maple-r88a-snap}"
HOOK_PREAPPLIED=0

mkdir -p "${OUT}"
for regime in ${REGIMES}; do mkdir -p "${OUT}/${regime}"; done

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
  echo "### base arm = ${SRC} at ${BASE_SHA:0:8}; delta vs HEAD:"
  git diff --stat HEAD -- "${SRC}"
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
  local dir="$1" tag="$2" arm="$3" regime="$4"
  local split=""
  [ "${regime}" = "s1" ] && split="DARKBLOOM_GPU_PROFILE_SPLIT=1"
  env DECODE_PROBE_WORKER="${SNAP}/${arm}/mlxfast-runtime-worker" \
      DARKBLOOM_GPU_PROFILE=1 ${split} \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      --profile-top 12 --stderr "${dir}/${tag}.err" \
      --dump-steps "${dir}/${tag}.steps" \
      --dump-tokens "${dir}/${tag}.tokens" \
      >"${dir}/${tag}.log" 2>&1
}

echo "########## unscored warm-up run ##########"
run_slot "${OUT}" warmup base nat
echo "warm-up exit=$?"

slots=0
for arm in ${ORDER}; do slots=$((slots + 1)); done
nreg=0
for regime in ${REGIMES}; do nreg=$((nreg + 1)); done
echo "########## ${REPS} reps x ${nreg} regimes x ${slots} slots = "\
"$((REPS * nreg * slots)) runs ##########"

s1_idx=0
nat_idx=0

for rep in $(seq 1 "${REPS}"); do
  order_regimes="${REGIMES}"
  if [ $((rep % 2)) -eq 0 ]; then
    order_regimes=""
    for regime in ${REGIMES}; do order_regimes="${regime} ${order_regimes}"; done
  fi
  for regime in ${order_regimes}; do
    for arm in ${ORDER}; do
      if [ "${regime}" = "s1" ]; then
        s1_idx=$((s1_idx + 1)); i="${s1_idx}"
      else
        nat_idx=$((nat_idx + 1)); i="${nat_idx}"
      fi
      tag=$(printf "%02d-rep%s-%s" "${i}" "${rep}" "${arm}")
      echo "=== ${regime}/${tag} ==="
      run_slot "${OUT}/${regime}" "${tag}" "${arm}" "${regime}"
      rc=$?
      grep -E "^decode steps=|^teacher-forced|^per steady step:" \
        "${OUT}/${regime}/${tag}.log" || echo "  (no summary; exit=${rc})"
    done
  done
done

echo "########## token identity across arms and regimes ##########"
cksum "${OUT}"/*/[0-9]*.tokens | awk '{print $1, $3}'
echo "########## done ##########"
