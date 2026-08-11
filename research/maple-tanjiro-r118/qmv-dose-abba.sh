#!/usr/bin/env bash
# R118-A: paired block-randomised in-situ byte dose on the shared-expert gate+up
# QMV, over DARKBLOOM_SHARED_QMV_ARM in {ship, ctl, d2, d1}.
#
# Arms (digits used in ORDER):
#   0 = ship  shipped kernel, shipped name, shipped source text
#   1 = ctl   byte-identical clone under a different kernel name (NEGATIVE
#             CONTROL; its paired interval must contain zero or the rig is dead)
#   2 = d2    reads 2 of the 4 512-wide K blocks  (-0.557 MB/call of unique
#             device bytes, -1.048 MB/call of input re-read traffic)
#   3 = d1    reads 1 of the 4 512-wide K blocks  (-0.836 MB/call unique)
#
# Ranking rule (mine, from R116-B): SPLIT=0, no GPU-profile hook at all.
# DARKBLOOM_GPU_PROFILE_SPLIT=1 inflates wall ~2x on this host and mis-ranks
# arms, so attribution and ranking never share a run.
#
# Design.  Each ORDER is N consecutive blocks of 4, every block a permutation of
# {0,1,2,3} drawn from a Latin square, so every arm appears exactly once per
# block (monotone session drift cancels in the block contrast) and exactly once
# in each within-block position per square (the first-in-block warmup penalty
# cancels too).  ORDER_A and ORDER_B are element-wise mirrors of each other and
# are analysed and reported SEPARATELY: agreement between the two mirrored
# orders is the credibility check, disagreement is a finding.
#
#   research/maple-tanjiro-r118/qmv-dose-abba.sh <ORDER> <OUT_DIR> [STEPS]
set -u
cd "$(dirname "$0")/../.."

ORDER="${1:?ORDER string of arm digits required}"
OUT="${2:?output dir required}"
STEPS="${3:-200}"
mkdir -p "${OUT}"
TSV="${OUT}/abba.tsv"
if [ ! -f "${TSV}" ]; then
  printf 'idx\tarm\tmean_ms\tmedian_ms\tp10_ms\tp90_ms\tdiverg\tload_s\n' > "${TSV}"
fi

WORKER=".build-worker/release/mlxfast-runtime-worker"
[ -x "${WORKER}" ] || { echo "no worker binary at ${WORKER}"; exit 3; }

for (( n=0; n<${#ORDER}; n++ )); do
  d="${ORDER:$n:1}"
  case "${d}" in
    0) arm=ship ;;
    1) arm=ctl ;;
    2) arm=d2 ;;
    3) arm=d1 ;;
    4) arm=rctl ;;
    5) arm=rd2 ;;
    6) arm=rd1 ;;
    *) echo "unknown arm digit ${d}"; exit 2 ;;
  esac
  i=$((n+1))
  log="${OUT}/run${i}_${arm}.log"
  echo "=== run ${i} arm ${arm} t=$(date -u +%H:%M:%S)"
  DARKBLOOM_SHARED_QMV_ARM="${arm}" python3 research/decode_probe.py \
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
