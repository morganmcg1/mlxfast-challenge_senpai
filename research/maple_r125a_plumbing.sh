#!/usr/bin/env bash
# R125-A plumbing check for the advisor's compiled-default-flip acceptance test.
#
# Delivered artifact under test = branch source
#   MINUS research/r125a-tg256-fused-guard.patch   (the fused-eligibility guard
#         must NOT ship with the flip: it would disable FUSED=1 once the default
#         width is 256, violating acceptance condition 2)
#   PLUS  research/r125a-tg256-default-flip.patch  (compiled default 64 -> 256)
#
# Stage A  instrumented build: prints the selected threadgroup width from the
#          scored dispatch so the compiled default is read directly, with no
#          environment variable set, and the env override is shown still live.
# Stage B  clean build of the same source: teacher-forced golden at the new
#          default, and a mirrored paired wall A/B of
#          "default-built binary, no env" vs "explicit DARKBLOOM_SHARED_QMV_TG=256".
#          Acceptance condition 4 asks only that these two be indistinguishable.
#
#   OUT=/tmp/maple-r125a-plumb bash research/maple_r125a_plumbing.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/maple-r125a-plumb}"
STEPS="${STEPS:-400}"
GATE_C="${GATE_C:-40.0}"
COOL_BUDGET="${COOL_BUDGET:-300}"
SRC="Sources/MLXFastModel/LagunaRuntimeModel.swift"
mkdir -p "${OUT}"

if ! git diff --quiet -- Sources Vendor; then
  echo "refusing: Sources/Vendor are dirty" >&2
  exit 2
fi
echo "### HEAD: $(git rev-parse HEAD)"

restore() { git checkout -- "${SRC}" 2>/dev/null || true; }
trap restore EXIT

apply_delivered() {
  git apply -R research/r125a-tg256-fused-guard.patch || return 1
  git apply research/r125a-tg256-default-flip.patch || return 1
  grep -n "else { return 256 }" "${SRC}" | head -1
  echo -n "fused guard lines still present: "
  grep -c "lagunaSharedSwiGLUQMVThreadgroupWidth == 64" "${SRC}"
}

build_worker() {
  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  local rc=$?
  git checkout -- Package.resolved 2>/dev/null || true
  return "${rc}"
}

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

########## stage A: read the compiled default directly ##########
echo "########## stage A: instrumented build ##########"
restore
apply_delivered || exit 3
awk '{print}
     /\? lagunaSharedSwiGLUQMVThreadgroupWidth : 64$/ {
       print "    FileHandle.standardError.write(\"R125A_TG=\\(threads)\\n\".data(using: .utf8)!)"
     }' "${SRC}" >"${OUT}/instrumented.swift" && mv "${OUT}/instrumented.swift" "${SRC}"
grep -n "R125A_TG=" "${SRC}"
build_worker || exit 4

probe_width() {
  local tag="$1"; shift
  env "$@" python3 research/decode_probe.py --steps 4 --prefill \
    --stderr "${OUT}/${tag}.err" >"${OUT}/${tag}.log" 2>&1
  local rc=$?
  echo "### ${tag} exit=${rc} observed_widths=$(grep -o 'R125A_TG=[0-9]*' "${OUT}/${tag}.err" 2>/dev/null | sort -u | tr '\n' ' ')"
}
probe_width A_no_env
probe_width A_env64  DARKBLOOM_SHARED_QMV_TG=64
probe_width A_env128 DARKBLOOM_SHARED_QMV_TG=128

########## stage B: clean delivered build ##########
echo "########## stage B: clean delivered build ##########"
restore
apply_delivered || exit 5
build_worker || exit 6

echo "########## teacher-forced golden at the new compiled default (no env) ##########"
python3 research/decode_probe.py \
  --steps 200 --prefill --stderr "${OUT}/tf_default.err" \
  --dump-tokens "${OUT}/tf_default.tokens" 2>&1 \
  | tee "${OUT}/tf_default.log" | grep -E "teacher-forced|diverg|prefill|decode steps"
DARKBLOOM_SHARED_QMV_TG=64 python3 research/decode_probe.py \
  --steps 200 --prefill --stderr "${OUT}/tf_tg64.err" \
  --dump-tokens "${OUT}/tf_tg64.tokens" 2>&1 \
  | tee "${OUT}/tf_tg64.log" | grep -E "teacher-forced|diverg|prefill|decode steps"
if cmp -s "${OUT}/tf_default.tokens" "${OUT}/tf_tg64.tokens"; then
  echo "tf: default == explicit TG64 TOKENS_IDENTICAL"
else
  echo "tf: TOKENS_DIFFER"
fi

echo "########## paired wall: default (no env) vs explicit TG=256 ##########"
run_slot() {
  local tag="$1"; shift
  cool_wait
  env "$@" python3 research/decode_probe.py --steps "${STEPS}" --prefill \
    --stderr "${OUT}/${tag}.err" --dump-steps "${OUT}/${tag}.steps" \
    --dump-tokens "${OUT}/${tag}.tokens" >"${OUT}/${tag}.log" 2>&1
  local rc=$?
  echo "### ${tag} exit=${rc} $(grep -E '^decode steps' "${OUT}/${tag}.log" || true)"
  rm -f "${OUT}/${tag}.err"
}
run_slot p1_dflt
run_slot p2_e256  DARKBLOOM_SHARED_QMV_TG=256
run_slot p3_e256  DARKBLOOM_SHARED_QMV_TG=256
run_slot p4_dflt

for t in p2_e256 p3_e256 p4_dflt; do
  if cmp -s "${OUT}/p1_dflt.tokens" "${OUT}/${t}.tokens"; then
    echo "${t} TOKENS_IDENTICAL"
  else
    echo "${t} TOKENS_DIFFER"
  fi
done

restore
echo "### restored: $(git status --porcelain -- Sources Vendor | wc -l | tr -d ' ') dirty source paths"
