#!/usr/bin/env bash
# R119-B: dispatch-count delta, per-kernel attribution, and the occupancy proxy
# for the grid-appended shared+routed gate/up QMV.
#
# Uses research/nezuko-pr158-gpuprof-hook.patch, which additionally prints
# `GPUPSO <name> maxThreads= execWidth= tgMem=` at pipeline creation --
# maxTotalThreadsPerThreadgroup is the register-pressure proxy the assignment
# requires for the register-union gate.
#
# SPLIT=0 keeps the shipped command-buffer batching policy, so its dispatch
# counts and wall are the honest ones. SPLIT=1 puts one dispatch per command
# buffer: attribution only, inflated by per-command-buffer overhead.
#
# Research-only; not on editablePaths.
#   OUT=/tmp/edward-r119b-prof STEPS=120 bash research/edward_r119b_profile.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/edward-r119b-prof}"
STEPS="${STEPS:-120}"
TOP="${TOP:-26}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty; commit before profiling" >&2
  exit 2
fi
echo "### HEAD: $(git rev-parse HEAD)"

cleanup() {
  echo "### reverting GPU-profile hook"
  git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
}
git apply "${PATCH}" || exit 3
trap cleanup EXIT

echo "### building worker (HEAD + gpuprof hook)"
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
[ "${rc}" -eq 0 ] || exit 4

run_slot() {
  local tag="$1" gate="$2" split="$3"
  DARKBLOOM_SHARED_ROUTED_QMV_FUSED="${gate}" \
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="${split}" \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      --profile-top "${TOP}" --stderr "${OUT}/${tag}.err" \
      --dump-steps "${OUT}/${tag}.steps" \
      --dump-tokens "${OUT}/${tag}.tokens" \
      >"${OUT}/${tag}.log" 2>&1
  echo "### ${tag} gate=${gate} split=${split} exit=$?"
}

echo "########## unscored warm-up ##########"
run_slot warmup 1 0
for slot in s0_off s0_on s1_off s1_on; do
  case "${slot}" in
    s0_off) run_slot "${slot}" 0 0 ;;
    s0_on)  run_slot "${slot}" 1 0 ;;
    s1_off) run_slot "${slot}" 0 1 ;;
    s1_on)  run_slot "${slot}" 1 1 ;;
  esac
done

for t in s0_off s0_on s1_off s1_on; do
  echo "===================== ${t} ====================="
  grep -E "teacher-forced|per steady step|profile:" "${OUT}/${t}.log"
  echo "--- top kernels"
  sed -n '/us\/step/,$p' "${OUT}/${t}.log" | head -30
  echo "--- GPUPSO for the three QMV kernels"
  grep -E "GPUPSO .*(shared_nvfp4_swiglu_qmv|routed_nvfp4_swiglu_qmv|shared_routed_nvfp4_swiglu_qmv)" \
    "${OUT}/${t}.err" | sort -u
done

echo "### token identity across gate arms (split=0)"
cmp -s "${OUT}/s0_off.tokens" "${OUT}/s0_on.tokens" \
  && echo TOKENS_IDENTICAL || echo TOKENS_DIFFER
