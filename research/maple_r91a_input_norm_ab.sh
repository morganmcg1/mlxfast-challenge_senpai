#!/usr/bin/env bash
# Research-only (PR #483, R91-A stage 1): counterbalanced ABBA that prices the
# WHOLE input-RMSNorm -> QKV fusion prize by deleting the per-layer input-norm
# dispatch outright. The deletion arms are numerically WRONG; they are a
# ceiling instrument, never a shipping candidate.
#
# Arms (one binary, selected by DARKBLOOM_R91_INPUT_NORM_PROBE -- see
# Sources/MLXFastModel/LagunaRuntimeModel.swift:5306-5322,:5789-5799):
#
#   base   0   shipped `inputNorm(input)` before the NVFP4 QKV GEMV.
#   skipr -1   QKV/gate consume the raw residual. Removes exactly one dispatch
#              per layer and preserves every producer/consumer edge, so the
#              dispatch stream stays serialised exactly as shipped. PRIMARY.
#   skipc -2   QKV/gate consume the norm weight broadcast to the row shape.
#              Bounded values, but the projection subchain no longer depends on
#              the previous layer, so it may overlap. Diagnostic bracket only.
#   dupn   2   two independent input norms per layer reduced by an element-wise
#              `maximum`. Bit-exact (`max(x,x) == x`), so no downstream value,
#              route or gather moves. PRIMARY, confound-free.
#   max1   3   one input norm, same `maximum` reduction against itself: the
#              matched control for `dupn`. `dupn - max1` = one norm dispatch.
#
# Rule 33 does not bite: no kernel SOURCE differs between arms, only how many
# times the unchanged `rms_single_row` AOT kernel is dispatched, so there is no
# MLX JIT cache key to collide.
#
# Regimes:
#   nat  DARKBLOOM_GPU_PROFILE=1              ~45 CBs/step, shipped dispatch
#        concurrency. The only regime a conclusion may be drawn from.
#   s1   ... plus DARKBLOOM_GPU_PROFILE_SPLIT=1, 406 CBs/step, one dispatch per
#        command buffer. ATTRIBUTION ONLY (rule 43): no s1 total, ratio or
#        cross-kernel sum may enter a conclusion.
#
# The default ORDER is an 8-slot palindrome giving, per rep, 2 base/skipr
# duplexes, 2 base/skipc duplexes, 2 skipr/skipc duplexes and 1 base/base null.
#
#   OUT=/tmp/maple-r91a REPS=4 REGIMES=nat bash research/maple_r91a_input_norm_ab.sh
#
# The bit-exact stage-1b ORDER is "base max1 max1 base dupn max1 max1 dupn",
# which at REPS=4 yields n=8 for base|max1 at offset 0, n=8 for max1|dupn at
# offset 0, n=8 sign-balanced for base|dupn at offset 1 (its duplexes straddle
# the rep boundary) and n=8 max1|max1 nulls at offset 1.
set -uo pipefail

OUT="${OUT:-/tmp/maple-r91a}"
REPS="${REPS:-4}"
STEPS="${STEPS:-200}"
ORDER="${ORDER:-base skipr skipc base base skipc skipr base}"
REGIMES="${REGIMES:-nat}"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
WORKER="${PWD}/.build-worker/release/mlxfast-runtime-worker"
HOOK_PREAPPLIED=0

arm_mode() {
  case "$1" in
    base) echo 0 ;;
    skipr) echo -1 ;;
    skipc) echo -2 ;;
    dupn) echo 2 ;;
    max1) echo 3 ;;
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}

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

cleanup() {
  if [ "${HOOK_PREAPPLIED}" = "1" ]; then
    echo "### GPU-profile hook was already applied on entry; leaving it"
  else
    echo "### reverting GPU-profile hook"
    git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
    build_worker "restore" || echo "WARNING: restore build failed"
  fi
}

if ! git diff --quiet -- "${SRC}"; then
  echo "refusing: ${SRC} is dirty; commit before timing" >&2
  exit 2
fi

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

build_worker "single binary (HEAD + gpuprof hook)" || exit 4
shasum -a 256 "${WORKER}" | tee "${OUT}/binary.sha256"

run_slot() {
  local dir="$1" tag="$2" arm="$3" regime="$4" steps="$5"
  local split=""
  [ "${regime}" = "s1" ] && split="DARKBLOOM_GPU_PROFILE_SPLIT=1"
  env DECODE_PROBE_WORKER="${WORKER}" \
      DARKBLOOM_R91_INPUT_NORM_PROBE="$(arm_mode "${arm}")" \
      DARKBLOOM_GPU_PROFILE=1 ${split} \
    python3 research/decode_probe.py --steps "${steps}" --profile \
      --profile-top 16 --stderr "${dir}/${tag}.err" \
      --dump-steps "${dir}/${tag}.steps" \
      --dump-tokens "${dir}/${tag}.tokens" \
      >"${dir}/${tag}.log" 2>&1
}

echo "########## reachability pre-check (rule 39): dispatches/step per arm ##########"
mkdir -p "${OUT}/precheck"
PRECHECK_ARMS="${PRECHECK_ARMS:-$(printf '%s\n' ${ORDER} | sort -u | tr '\n' ' ')}"
for arm in ${PRECHECK_ARMS}; do
  run_slot "${OUT}/precheck" "00-rep0-${arm}" "${arm}" nat 24
  printf '%-6s ' "${arm}"
  grep -E "^per steady step:" "${OUT}/precheck/00-rep0-${arm}.log" \
    || echo "  (no summary)"
done

echo "########## unscored warm-up run ##########"
run_slot "${OUT}" warmup base nat "${STEPS}"
echo "warm-up exit=$?"

slots=0
for arm in ${ORDER}; do slots=$((slots + 1)); done
nreg=0
for regime in ${REGIMES}; do nreg=$((nreg + 1)); done
echo "########## ${REPS} reps x ${nreg} regimes x ${slots} slots ="\
" $((REPS * nreg * slots)) runs ##########"

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
      run_slot "${OUT}/${regime}" "${tag}" "${arm}" "${regime}" "${STEPS}"
      rc=$?
      grep -E "^decode steps=|^teacher-forced|^per steady step:" \
        "${OUT}/${regime}/${tag}.log" || echo "  (no summary; exit=${rc})"
    done
  done
done

echo "########## token checksums (arms diverge by construction) ##########"
cksum "${OUT}"/*/[0-9]*.tokens | awk '{print $1, $3}'
echo "########## done ##########"
