#!/usr/bin/env bash
# Research-only (PR #714, R119-C): SPLIT=1 per-kernel atlas for the three
# shared-expert SwiGLU QMV threadgroup-width arms (64 / 128 / 256 threads).
#
# The arms are byte-identical in work; only the static threadgroup -> core
# assignment granularity differs. Mirrored ABC|CBA blocks so any thermal or
# session drift is orthogonal to arm order.
#
#   OUT=research/r119c-runs/atlas BLOCKS=3 bash research/maple_r119c_atlas.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-research/r119c-runs/atlas}"
STEPS="${STEPS:-200}"
BLOCKS="${BLOCKS:-3}"
TOP="${TOP:-44}"
PATCH="research/nezuko-pr158-gpuprof-hook.patch"
MACMON="${HOME}/bin/macmon"
mkdir -p "${OUT}"

thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{gpu_temp:.temp.gpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

cool() {
  for _ in $(seq 1 60); do
    local t
    t="$("${MACMON}" pipe -s1 2>/dev/null | jq -r '.temp.gpu_temp_avg' 2>/dev/null)"
    case "${t}" in
      ''|null) return 0 ;;
    esac
    if [ "$(printf '%.0f' "${t}")" -le 40 ]; then return 0; fi
    sleep 10
  done
}

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty" >&2
  exit 2
fi
echo "### HEAD: $(git rev-parse HEAD)"

cleanup() {
  echo "### reverting GPU-profile hook"
  git apply -R "${PATCH}" || echo "WARNING: hook revert failed"
}
git apply "${PATCH}" || exit 3
trap cleanup EXIT

echo "### building hooked worker"
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
[ "${rc}" -eq 0 ] || exit 4

run_slot() {
  local tag="$1" tg="$2"
  cool
  echo "=== ${tag} TG=${tg} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
  DARKBLOOM_SHARED_QMV_TG="${tg}" \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      --profile-top "${TOP}" --stderr "${OUT}/${tag}.err" \
      >"${OUT}/${tag}.log" 2>&1
  local rc=$?
  echo "--- ${tag} rc=${rc}"
  grep -E "per steady step:|teacher-forced|swiglu_qmv_rows1_halved" \
    "${OUT}/${tag}.log" | head -4
  [ "${rc}" -eq 0 ] && rm -f "${OUT}/${tag}.err"
}

echo "########## unscored warm-up ##########"
run_slot warmup 64

pos=0
for b in $(seq 1 "${BLOCKS}"); do
  for tg in 64 128 256 256 128 64; do
    run_slot "$(printf 'p%02d-tg%s' "${pos}" "${tg}")" "${tg}"
    pos=$((pos + 1))
  done
done
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
