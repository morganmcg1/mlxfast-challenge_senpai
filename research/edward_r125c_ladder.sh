#!/usr/bin/env bash
# R125-C paired threads-per-threadgroup ladder for the routed gate/up QMV,
# ranked on the end-to-end SPLIT=0 decode wall.
#
# One binary. The arm is DARKBLOOM_ROUTED_QMV_TG, read once per worker process.
# The grid stays at 131072 threads in every arm, so the simdgroup count is
# pinned at 4096 and only the threadgroup partition changes:
#
#   A  unset (64 threads/TG,  2 simdgroups/TG, 2048 threadgroups)  shipped
#   B  128   (128 threads/TG, 4 simdgroups/TG, 1024 threadgroups)
#   D  256   (256 threads/TG, 8 simdgroups/TG,  512 threadgroups)
#   N  negative control: labelled N but run with the shipped default, so an
#      N-vs-A contrast is byte-identical work inside the same block structure.
#
# Blocking: ORDER is consumed one character per run; BLOCK runs form a block.
# The supplied default order uses palindromic blocks, so each arm's two runs in
# a block are symmetric about the block centre and a linear thermal drift
# cancels within the block.
#
# Research-only; not on editablePaths.
#   OUT=/tmp/r125c-ladder ORDER=ABDDBA... STEPS=512 bash research/edward_r125c_ladder.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/r125c-ladder}"
# Six palindromic blocks. Each arm holds the {1,6}, {2,5} and {3,4} slot pair
# exactly twice across the campaign, so slot occupancy is balanced per arm.
ORDER="${ORDER:-ABDDBABDAADBDABBADADBBDADBAABDBADDAB}"
STEPS="${STEPS:-512}"
BLOCK="${BLOCK:-6}"
TAG="${TAG:-ladder}"
mkdir -p "${OUT}"
export PATH="${HOME}/.local/bin:${PATH}"
export MLXFAST_LOCAL_FAN_PROMPT=0
CSV="${OUT}/${TAG}_raw.csv"
SUM="${OUT}/${TAG}_runs.tsv"
printf 'order_tag,block,run,arm,step,ms\n' > "${CSV}"
printf 'order_tag\tblock\trun\tarm\tsteps\tmedian_ms\tmean_ms\tdivergences\n' > "${SUM}"

if [ "${WARMUP:-1}" = "1" ]; then
  echo "### unscored warm-up (page-in + thermal ramp)"
  python3 research/decode_probe.py --steps "${STEPS}" \
      --stderr "${OUT}/${TAG}_warmup.err" >"${OUT}/${TAG}_warmup.log" 2>&1
  echo "### warm-up exit=$? $(grep -o 'median=[0-9.]*' "${OUT}/${TAG}_warmup.log" | tail -1)"
fi

for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  run=$((n+1))
  block=$((n/BLOCK+1))
  case "${arm}" in
    A) tg= ;;
    B) tg=128 ;;
    D) tg=256 ;;
    N) tg= ;;
    *) echo "bad arm ${arm}" >&2; exit 2 ;;
  esac
  log="${OUT}/${TAG}_${run}_${arm}.log"
  steps_file="${OUT}/${TAG}_${run}_${arm}.steps"
  DARKBLOOM_ROUTED_QMV_TG="${tg}" \
    python3 research/decode_probe.py --steps "${STEPS}" \
      --stderr "${OUT}/${TAG}_${run}_${arm}.err" \
      --dump-steps "${steps_file}" \
      --dump-tokens "${OUT}/${TAG}_${run}_${arm}.tokens" \
      >"${log}" 2>&1
  rc=$?
  div=$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "${log}" \
        | tail -1 | awk '{print $4}')
  med=$(grep -o 'median=[0-9.]*' "${log}" | tail -1 | cut -d= -f2)
  mea=$(grep -o 'mean=[0-9.]*' "${log}" | tail -1 | cut -d= -f2)
  # Step 0 pays the one-time KV growth concat, so it is never a sample.
  awk -v o="${TAG}" -v b="${block}" -v r="${run}" -v a="${arm}" \
      'NR>1 { printf "%s,%d,%d,%s,%d,%s\n", o, b, r, a, NR-1, $1 }' \
      "${steps_file}" >> "${CSV}" 2>/dev/null
  printf '%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\n' \
    "${TAG}" "${block}" "${run}" "${arm}" "${STEPS}" "${med:-NA}" \
    "${mea:-NA}" "${div:-NA}" | tee -a "${SUM}"
  [ "${rc}" -eq 0 ] || echo "### run ${run} (${arm}) exit=${rc}"
done

echo "--- ${SUM} ---"
cat "${SUM}"
echo "raw samples: $(( $(wc -l < "${CSV}") - 1 ))"
