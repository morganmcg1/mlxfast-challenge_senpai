#!/usr/bin/env bash
# R119-B paired ABBA / BAAB campaign for the shared+routed gate/up QMV
# grid-append, ranked on the end-to-end SPLIT=0 decode wall.
#
# One binary. The arm is an environment flag read once per worker process, so
# the only difference between arms is which dispatch shape the scored decode
# path takes:
#
#   C  DARKBLOOM_SHARED_ROUTED_QMV_FUSED=0   shipped two dispatches
#   F  DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1   one grid-appended dispatch
#   N  negative control: labelled F, but the gate is forced to 0, so the two
#      labels are byte-identical work in the same block structure
#
# Blocking: the ORDER string is consumed 4 characters at a time, one block per
# quadruple, so CFFC is an ABBA block and FCCF is its mirror. Every worker
# process dumps its raw per-step milliseconds, so the CSV carries every sample.
#
# Research-only; not on editablePaths.
#   OUT=/tmp/r119b-abba ORDER=CFFCCFFC... STEPS=256 bash research/edward_r119b_abba.sh
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT="${OUT:-/tmp/r119b-abba}"
ORDER="${ORDER:-CFFC}"
STEPS="${STEPS:-256}"
TAG="${TAG:-abba}"
mkdir -p "${OUT}"
CSV="${OUT}/${TAG}_raw.csv"
SUM="${OUT}/${TAG}_runs.tsv"
printf 'order_tag,block,run,arm,step,ms\n' > "${CSV}"
printf 'order_tag\tblock\trun\tarm\tsteps\tmedian_ms\tmean_ms\tdivergences\n' > "${SUM}"

for (( n=0; n<${#ORDER}; n++ )); do
  arm="${ORDER:$n:1}"
  run=$((n+1))
  block=$((n/4+1))
  case "${arm}" in
    C) gate=0 ;;
    F) gate=1 ;;
    N) gate=0 ;;
    *) echo "bad arm ${arm}" >&2; exit 2 ;;
  esac
  log="${OUT}/${TAG}_${run}_${arm}.log"
  steps_file="${OUT}/${TAG}_${run}_${arm}.steps"
  DARKBLOOM_SHARED_ROUTED_QMV_FUSED="${gate}" \
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
