#!/usr/bin/env bash
# R125-A closing leg: SPLIT=0 paired *wall* A/B for DARKBLOOM_SHARED_QMV_TG.
#
# The atlas (research/maple_r125a_atlas.sh) runs with DARKBLOOM_GPU_PROFILE_SPLIT=1,
# which serialises dispatches and therefore measures isolated per-kernel GPU busy
# time.  A wider threadgroup could in principle cost more busy time yet still win
# wall time by freeing scheduler slots.  This script closes that gap: no profile
# hook, no split, plain end-to-end decode wall time, mirrored 64/256/256/64 blocks.
#
#   OUT=/tmp/maple-r125a-wall STEPS=400 BLOCKS=4 bash research/maple_r125a_wall.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/maple-r125a-wall}"
STEPS="${STEPS:-400}"
BLOCKS="${BLOCKS:-4}"
GATE_C="${GATE_C:-40.0}"
COOL_BUDGET="${COOL_BUDGET:-300}"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty (is the gpuprof hook still applied?)" >&2
  exit 2
fi
echo "### HEAD: $(git rev-parse HEAD)"

echo "### building hook-free worker"
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
rc=$?
git checkout -- Package.resolved 2>/dev/null || true
[ "${rc}" -eq 0 ] || exit 3

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
    python3 research/decode_probe.py --steps "${STEPS}" --prefill \
      --stderr "${OUT}/${tag}.err" \
      --dump-steps "${OUT}/${tag}.steps" \
      --dump-tokens "${OUT}/${tag}.tokens" \
      >"${OUT}/${tag}.log" 2>&1
  local rc=$?
  echo "### ${tag} tg=${tg} exit=${rc} gpu_at_start=${t0}C $(grep -E '^decode steps' "${OUT}/${tag}.log" || true)"
  rm -f "${OUT}/${tag}.err"
}

echo "########## unscored warm-up ##########"
run_slot warmup 64

for b in $(seq 1 "${BLOCKS}"); do
  echo "########## block ${b} (64 256 256 64) ##########"
  run_slot "b${b}_s1_tg64" 64
  run_slot "b${b}_s2_tg256" 256
  run_slot "b${b}_s3_tg256" 256
  run_slot "b${b}_s4_tg64" 64
done

echo "########## token identity ##########"
for b in $(seq 1 "${BLOCKS}"); do
  for s in s2_tg256 s3_tg256 s4_tg64; do
    if cmp -s "${OUT}/b${b}_s1_tg64.tokens" "${OUT}/b${b}_${s}.tokens"; then
      echo "b${b}_${s} TOKENS_IDENTICAL"
    else
      echo "b${b}_${s} TOKENS_DIFFER"
    fi
  done
done
