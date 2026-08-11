#!/usr/bin/env bash
# R125-E: shipped-default env-knob sweep on the live composition.
#
# One arm = one worker process, because every DARKBLOOM_* knob is a file-scope
# Swift `let` and is therefore parsed once per process. The arm label selects the
# env delta; everything else stays at the shipped default. Position in the ORDER
# string is the only other difference between two runs of the same arm, which is
# why the caller must counterbalance it.
#
# Research-only; not on editablePaths.
#
#   OUT=/tmp/r125e ORDER="C FUS C PF0" STEPS=224 bash research/frieren_r125e_arms.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/r125e}"
ORDER="${ORDER:-C FUS}"
STEPS="${STEPS:-224}"
TAG="${TAG:-screen}"
PROFILE="${PROFILE:-full}"   # DARKBLOOM_STARTUP_MEMORY_PROFILE; "" = host default
WARMUP="${WARMUP:-1}"
mkdir -p "${OUT}"
CSV="${OUT}/${TAG}_raw.csv"
SUM="${OUT}/${TAG}_runs.tsv"
[ -f "${CSV}" ] || printf 'tag,run,arm,step,ms\n' > "${CSV}"
[ -f "${SUM}" ] || printf 'tag\trun\tarm\tsteps\tmedian_ms\tmean_ms\tdivergences\tseed_ms\tload_s\trc\n' > "${SUM}"

arm_env() {
  # echoes zero or more KEY=VALUE tokens for the arm label
  case "$1" in
    C)      ;;                                                     # shipped default
    FUS)    echo "DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1" ;;
    PF0)    echo "DARKBLOOM_NORM_AFFINE_QKV_PF=0" ;;
    PF1)    echo "DARKBLOOM_NORM_AFFINE_QKV_PF=1" ;;
    PF2)    echo "DARKBLOOM_NORM_AFFINE_QKV_PF=2" ;;
    PF3)    echo "DARKBLOOM_NORM_AFFINE_QKV_PF=3" ;;
    U1)     echo "DARKBLOOM_L5_UNROLL=1" ;;
    U4)     echo "DARKBLOOM_L5_UNROLL=4" ;;
    U8)     echo "DARKBLOOM_L5_UNROLL=8" ;;
    RP0)    echo "DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0" ;;
    RP5)    echo "DARKBLOOM_ROUTER_WEIGHT_PREFETCH=5" ;;
    NS0)    echo "DARKBLOOM_NVFP4_NIBBLE_SPLIT=0" ;;
    NS2)    echo "DARKBLOOM_NVFP4_NIBBLE_SPLIT=2" ;;
    STG)    echo "DARKBLOOM_NORM_AFFINE_QKV_STAGE=tg" ;;
    STGPF)  echo "DARKBLOOM_NORM_AFFINE_QKV_STAGE=tg DARKBLOOM_NORM_AFFINE_QKV_PF=4" ;;
    ASOFF)  echo "DARKBLOOM_DECODE_ASYNC_STAGE=off" ;;
    ASDEN)  echo "DARKBLOOM_DECODE_ASYNC_STAGE=at:0,1,3,7,11,15,19,23,27,31,35,39" ;;
    ASSPA)  echo "DARKBLOOM_DECODE_ASYNC_STAGE=at:0,1,15,31" ;;
    ASLAD)  echo "DARKBLOOM_DECODE_ASYNC_STAGE=ladder8" ;;
    ASNRM)  echo "DARKBLOOM_DECODE_ASYNC_STAGE=norm" ;;
    OPR1)   echo "DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=1" ;;
    OPR4)   echo "DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP=4" ;;
    OPSG4)  echo "DARKBLOOM_OPROJ_SIMDGROUPS=4" ;;
    *)      echo "__BAD__" ;;
  esac
}

run_arm() {
  local arm="$1" run="$2"
  local -a envs=()
  local tok
  for tok in $(arm_env "${arm}"); do
    if [ "${tok}" = "__BAD__" ]; then echo "bad arm ${arm}" >&2; return 2; fi
    envs+=("${tok}")
  done
  [ -n "${PROFILE}" ] && envs+=("DARKBLOOM_STARTUP_MEMORY_PROFILE=${PROFILE}")
  local log="${OUT}/${TAG}_${run}_${arm}.log"
  local steps_file="${OUT}/${TAG}_${run}_${arm}.steps"
  env "${envs[@]}" python3 research/decode_probe.py --steps "${STEPS}" \
      --stderr "${OUT}/${TAG}_${run}_${arm}.err" \
      --dump-steps "${steps_file}" >"${log}" 2>&1
  local rc=$?
  local div med mea seed load
  div=$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "${log}" | tail -1 | awk '{print $4}')
  med=$(grep -o 'median=[0-9.]*' "${log}" | tail -1 | cut -d= -f2)
  mea=$(grep -o 'mean=[0-9.]*' "${log}" | tail -1 | cut -d= -f2)
  seed=$(grep -o 'decode_begin seed forward: [0-9.]*' "${log}" | tail -1 | awk '{print $4}')
  load=$(grep -o 'worker up in [0-9.]*' "${log}" | tail -1 | awk '{print $4}')
  # step 0 pays the one-time KV growth concat, so it is never a sample
  awk -v t="${TAG}" -v r="${run}" -v a="${arm}" \
      'NR>1 { printf "%s,%d,%s,%d,%s\n", t, r, a, NR-1, $1 }' \
      "${steps_file}" >> "${CSV}" 2>/dev/null
  printf '%s\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\n' \
    "${TAG}" "${run}" "${arm}" "${STEPS}" "${med:-NA}" "${mea:-NA}" \
    "${div:-NA}" "${seed:-NA}" "${load:-NA}" "${rc}" | tee -a "${SUM}"
}

if [ "${WARMUP}" = "1" ]; then
  echo "### unscored warm-up (page-in + thermal ramp)"
  run_arm C 0 >/dev/null 2>&1
fi

run=0
for arm in ${ORDER}; do
  run=$((run+1))
  run_arm "${arm}" "${run}"
done

echo "--- ${SUM} ---"
cat "${SUM}"
