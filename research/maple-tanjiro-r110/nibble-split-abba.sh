#!/usr/bin/env bash
# R116-B step 2: paired ABBA over DARKBLOOM_NVFP4_NIBBLE_SPLIT in {0,1,2}.
#
# The flag (LagunaRuntimeModel.swift:6651-6657) picks one of three FP4 nibble
# -> half2 unpacking sequences at :6779-6809.  That block is inlined twice per
# `laguna_nvfp4_qdot_codes_16` call (:6884-6890) and the enclosing header feeds
# 17 kernel registrations, so the arm difference is spread over the whole NVFP4
# QMV family, not just the named target.
#
# Ranking rule: SPLIT=0 (no GPU-profile hook at all).  My own instrument result
# is that DARKBLOOM_GPU_PROFILE_SPLIT=1 inflates wall by +19.6 % and MIS-RANKS
# arms, so attribution and ranking must not share a run.  Profiled runs are a
# separate script.
#
# Design.  ORDER is 12 consecutive blocks of 3, each block a permutation of
# {0,1,2}.  Every arm therefore appears exactly once in every block, so all
# three arms have an identical mean slot and any monotone session drift cancels
# exactly in the block contrast rather than approximately.  The 6 distinct
# permutations are each used twice, so each arm also occupies each within-block
# position exactly 4 times -- that balances the first-in-block warmup penalty
# too, which the Stage 0 rig could only balance on average.
#
# Every arm is set explicitly, including arm 1.  Arm 1 is the shipped default,
# but leaving it unset would make it the one arm that takes the `else` branch
# of the env parse; setting it keeps the three arms structurally identical.
#
#   research/maple-tanjiro-r110/nibble-split-abba.sh [ORDER] [OUT_DIR] [STEPS]
set -u
cd "$(dirname "$0")/../.."

ORDER="${1:-012120201021210102102210021201120012}"
OUT="${2:-/tmp/r116b-abba}"
STEPS="${3:-200}"
mkdir -p "${OUT}"
TSV="${OUT}/abba.tsv"
printf 'idx\tarm\tmean_ms\tmedian_ms\tp10_ms\tp90_ms\tdiverg\tload_s\n' > "${TSV}"

# Rebuild from the current worktree.  The reachability script leaves an
# instrumented binary in .build-worker; ranking must not run against it.
echo "=== build worker t=$(date -u +%H:%M:%S)"
if ! git diff --quiet -- Sources/MLXFastModel/LagunaRuntimeModel.swift; then
  echo "REFUSING: LagunaRuntimeModel.swift is dirty; ranking needs the clean tree"
  git --no-pager diff --stat -- Sources/MLXFastModel/LagunaRuntimeModel.swift
  exit 4
fi
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
    0|1|2) : ;;
    *) echo "unknown arm ${arm}"; exit 2 ;;
  esac
  echo "=== run ${i} arm ${arm} t=$(date -u +%H:%M:%S)"
  DARKBLOOM_NVFP4_NIBBLE_SPLIT="${arm}" python3 research/decode_probe.py \
      --steps "${STEPS}" --dump-steps "${OUT}/run${i}_${arm}.steps" \
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
