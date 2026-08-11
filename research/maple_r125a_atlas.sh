#!/usr/bin/env bash
# R125-A: replicate frieren's R119-C shared-expert SwiGLU QMV threadgroup-width
# arms on the maple advisor base, with the same SPLIT=1 per-kernel GPU-busy
# instrument.
#
# Arms differ only in how 512 output rows (one row per simdgroup) are partitioned
# into threadgroups:
#   TG=64  -> 2 simdgroups/TG, 256 TGs   (shipped default)
#   TG=256 -> 8 simdgroups/TG,  64 TGs   (the geometry PR #729 proposes to land)
# The bytes read, the arithmetic and the output are byte-identical.
#
# Research-only; not on editablePaths. The GPUPROF hook is applied to the vendor
# for the measurement and reverted on exit.
#
#   OUT=/tmp/maple-r125a-atlas STEPS=200 BLOCKS=3 bash research/maple_r125a_atlas.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/maple-r125a-atlas}"
STEPS="${STEPS:-200}"
TOP="${TOP:-32}"
BLOCKS="${BLOCKS:-3}"
BLOCK0="${BLOCK0:-0}"
GATE_C="${GATE_C:-40.0}"
COOL_BUDGET="${COOL_BUDGET:-300}"
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

macmon="${HOME}/bin/macmon"
gpu_temp() {
  [[ -x "${macmon}" ]] || { echo "na"; return; }
  "${macmon}" pipe -s1 2>/dev/null | jq -r '.temp.gpu_temp_avg // empty' 2>/dev/null
}

cool_wait() {
  local t deadline=$(( $(date +%s) + COOL_BUDGET ))
  while (( $(date +%s) < deadline )); do
    t=$(gpu_temp)
    [[ -z "${t}" || "${t}" == "na" ]] && { echo "[cool] no macmon, continuing"; return 0; }
    awk -v v="${t}" -v g="${GATE_C}" 'BEGIN{exit !(v<=g)}' && {
      echo "[cool] gpu=${t}C <= ${GATE_C}C"; return 0; }
    echo "[cool] waiting for GPU to cool down (${t}C > ${GATE_C}C)"
    sleep 15
  done
  echo "[cool] gave up after ${COOL_BUDGET}s, gpu=$(gpu_temp)C"
}

run_slot() {
  local tag="$1" tg="$2"
  cool_wait
  local t0=$(gpu_temp)
  DARKBLOOM_SHARED_QMV_TG="${tg}" \
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py --steps "${STEPS}" --profile \
      --profile-top "${TOP}" --stderr "${OUT}/${tag}.err" \
      --dump-steps "${OUT}/${tag}.steps" \
      --dump-tokens "${OUT}/${tag}.tokens" \
      >"${OUT}/${tag}.log" 2>&1
  local rc=$?
  echo "### ${tag} tg=${tg} exit=${rc} gpu_at_start=${t0}C"
  grep -E "GPUPSO .*shared_nvfp4_swiglu_qmv" "${OUT}/${tag}.err" | sort -u \
    >"${OUT}/${tag}.pso"
  gzip -f "${OUT}/${tag}.err"
}

echo "########## unscored warm-up ##########"
run_slot warmup 64

for i in $(seq 1 "${BLOCKS}"); do
  b=$(( BLOCK0 + i ))
  echo "########## block ${b} (64 256 256 64) ##########"
  run_slot "b${b}_s1_tg64" 64
  run_slot "b${b}_s2_tg256" 256
  run_slot "b${b}_s3_tg256" 256
  run_slot "b${b}_s4_tg64" 64
done

echo "########## token identity ##########"
for i in $(seq 1 "${BLOCKS}"); do
  b=$(( BLOCK0 + i ))
  for s in s2_tg256 s3_tg256 s4_tg64; do
    if cmp -s "${OUT}/b${b}_s1_tg64.tokens" "${OUT}/b${b}_${s}.tokens"; then
      echo "b${b}_${s} TOKENS_IDENTICAL"
    else
      echo "b${b}_${s} TOKENS_DIFFER"
    fi
  done
done

echo "########## dispatched pipelines ##########"
cat "${OUT}"/b*_*.pso | sort -u
