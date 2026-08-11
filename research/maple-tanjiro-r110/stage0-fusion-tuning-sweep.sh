#!/usr/bin/env bash
# R110-A rev4 Stage 0 addendum: attribute the fused kernel's give-back.
#
# The SPLIT=1 capture showed the fused norm+QKV kernel costs ~102 us/step more
# than `affine_qmv_fast` doing the same projections, against a norm-elimination
# prize of only ~77 us/step.  Two causes are confounded:
#   (1) redundant reduction -- each threadgroup recomputes the 2048-wide RMS,
#       and the kernel is 8 rows/TG (LagunaRuntimeModel.swift:5536-5542);
#   (2) kernel quality -- `norm_affine_qkv_qmv_i8g32_*` is a hand-written
#       MLXFast string kernel, `affine_qmv_fast` is MLX's tuned matvec.
#
# This sweep bounds (2).  If the shipped default PF=4 is already the best point
# of the tuning surface the author exposed, the give-back is not tuning debt and
# follow-up work would have to attack (1) with a new kernel shape.  If some
# other point is materially faster, part of the give-back is recoverable and the
# direction is worth reopening.
#
# Knobs, both read once at process start:
#   DARKBLOOM_NORM_AFFINE_QKV_PF     0..4, default 4   (:5225-5229)
#   DARKBLOOM_NORM_AFFINE_QKV_STAGE  "tg" enables the threadgroup-staged
#                                    variant, default off (:5205-5206)
#
# Arms (all on the group-32 affine INT8 bank, all one binary):
#   U = fusion off                         -- reference
#   4 3 2 1 0 = fusion on, PF = that digit
#   T = fusion on, PF=4, STAGE=tg
#
# ORDER default "U43210TT01234U" runs each arm twice at mirrored slots, so every
# arm has mean slot 7.5 and any monotone thermal drift cancels to first order.
#
#   research/maple-tanjiro-r110/stage0-fusion-tuning-sweep.sh [ORDER] [OUT] [STEPS]
set -u
cd "$(dirname "$0")/../.."

ORDER="${1:-U43210TT01234U}"
OUT="${2:-/tmp/r110a-sweep}"
STEPS="${3:-200}"
mkdir -p "${OUT}"
TSV="${OUT}/sweep.tsv"
printf 'idx\tarm\tmean_ms\tmedian_ms\tp10_ms\tp90_ms\tdiverg\tload_s\n' > "${TSV}"

echo "=== build worker t=$(date -u +%H:%M:%S)"
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker \
    > "${OUT}/build.log" 2>&1
rc=$?
git checkout -- Package.resolved 2>/dev/null
[ ${rc} -ne 0 ] && { echo "build failed rc=${rc}"; tail -40 "${OUT}/build.log"; exit 3; }
echo "=== build ok t=$(date -u +%H:%M:%S)"

for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  i=$((n+1))
  log="${OUT}/run${i}_${arm}.log"
  case "${arm}" in
    U) envargs=(DARKBLOOM_NATIVE_AFFINE_NVFP4=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0) ;;
    [0-4]) envargs=(DARKBLOOM_NATIVE_AFFINE_NVFP4=0 "DARKBLOOM_NORM_AFFINE_QKV_PF=${arm}") ;;
    T) envargs=(DARKBLOOM_NATIVE_AFFINE_NVFP4=0 DARKBLOOM_NORM_AFFINE_QKV_STAGE=tg) ;;
    *) echo "unknown arm ${arm}"; exit 2 ;;
  esac
  echo "=== run ${i} arm ${arm} t=$(date -u +%H:%M:%S)"
  env "${envargs[@]}" python3 research/decode_probe.py \
      --steps "${STEPS}" --stderr "${OUT}/run${i}_${arm}.err" > "${log}" 2>&1
  rc=$?
  mean=$(grep -o 'mean=[0-9.]*' "${log}" | head -1 | sed 's/mean=//')
  med=$(grep -o 'median=[0-9.]* ms' "${log}" | head -1 | sed 's/median=//;s/ ms//')
  p10=$(grep -o 'p10=[0-9.]* ms' "${log}" | head -1 | sed 's/p10=//;s/ ms//')
  p90=$(grep -o 'p90=[0-9.]* ms' "${log}" | head -1 | sed 's/p90=//;s/ ms//')
  div=$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "${log}" \
        | head -1 | awk '{print $4}')
  lds=$(grep -o 'worker up in [0-9.]*s' "${log}" | head -1 | awk '{print $4}')
  printf '%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${i}" "${arm}" "${mean:-NA}" "${med:-NA}" "${p10:-NA}" "${p90:-NA}" \
    "${div:-NA}" "${lds:-NA}" | tee -a "${TSV}"
  [ ${rc} -ne 0 ] && { echo "--- rc=${rc}, tail:"; tail -20 "${log}"; }
  rm -f "${OUT}/run${i}_${arm}.err"
done

echo "=== ${TSV} ==="
cat "${TSV}"
echo "=== done t=$(date -u +%H:%M:%S)"
