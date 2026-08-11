#!/usr/bin/env bash
# R110-A rev4 Stage 0: price the fused RMSNorm+QKV kernel that never runs.
#
# `lagunaNormAffineQKV` (LagunaRuntimeModel.swift:5488, call site :5933) is
# gated by six conditions at :5926-5931.  Two of them decline on the shipped
# NVFP4 bank: `fusedAffine.bits == 8 && groupSize == 32` (:5927-5928) and
# `_nativeAffineQKVGateRows == nHeads` (:5929, which only becomes nHeads when
# `foldGateIntoBank` at :5713 is true, and that also requires bits==8/g32).
# `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` makes `lagunaNativeAffineNVFP4From`
# (:3048-3054) return nil, so the consumer at :3101 falls through to :3115-3123
# `quantized(source, groupSize: 32, bits: 8, mode: .affine)` -- the group-32
# affine INT8 bank that TASK.md:78-94 permits -- and all six conditions hold.
#
# Both timed arms therefore run the SAME BINARY on the SAME BANK; the only
# difference is whether the fusion fires.  The int8 bank is slower than NVFP4
# overall, but that cost is common to both arms and cancels in the F-U
# contrast.  Arm N measures that common cost so it can be stated, not guessed.
#
# Arms (all one binary, no rebuild):
#   F = DARKBLOOM_NATIVE_AFFINE_NVFP4=0                                (fused)
#   U = DARKBLOOM_NATIVE_AFFINE_NVFP4=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0
#   N = shipped default (NVFP4 bank, fusion structurally unreachable)
#
# decode_probe.py passes `dict(os.environ)` straight to the worker binary
# (research/decode_probe.py:104,114), so no harness env allowlist applies here.
# It also reports teacher-forced divergences against the public golden, which
# is the fast signal for whether the int8 re-quantization moves any token.
#
# ORDER default `FUNUFFUNUF` is a palindrome whose three arms all have mean
# slot 5.5, so the known first-slot warmup penalty and any monotone session
# drift are balanced across F and U.
#
#   research/maple-tanjiro-r110/stage0-norm-qkv-abba.sh [ORDER] [OUT_DIR] [STEPS]
set -u
cd "$(dirname "$0")/../.."

ORDER="${1:-FUNUFFUNUF}"
OUT="${2:-/tmp/r110a-stage0}"
STEPS="${3:-200}"
mkdir -p "${OUT}"
TSV="${OUT}/abba.tsv"
printf 'idx\tarm\tmean_ms\tmedian_ms\tp10_ms\tp90_ms\tdiverg\tload_s\n' > "${TSV}"

# decode_probe.py runs the prebuilt worker and never builds it, so refresh it
# here the way benchmark.sh does; otherwise a stale binary can silently answer.
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
  steps="${OUT}/run${i}_${arm}.steps"
  case "${arm}" in
    F) envargs=(DARKBLOOM_NATIVE_AFFINE_NVFP4=0) ;;
    U) envargs=(DARKBLOOM_NATIVE_AFFINE_NVFP4=0 DARKBLOOM_FUSED_NORM_AFFINE_QKV=0) ;;
    N) envargs=() ;;
    *) echo "unknown arm ${arm}"; exit 2 ;;
  esac
  echo "=== run ${i} arm ${arm} t=$(date -u +%H:%M:%S)"
  env ${envargs[@]+"${envargs[@]}"} python3 research/decode_probe.py \
      --steps "${STEPS}" --dump-steps "${steps}" \
      --stderr "${OUT}/run${i}_${arm}.err" > "${log}" 2>&1
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
