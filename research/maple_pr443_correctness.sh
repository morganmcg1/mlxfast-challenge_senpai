#!/usr/bin/env bash
# Research-only (PR #443): liveness + correctness battery for
# `DARKBLOOM_SHARED_SCALE_HALVED`.
#
# Stage 0 (liveness) and stage 2 (correctness) share one worker process per arm,
# so the same run proves the arm reached the scored kernel and matched the
# golden. Per arm it records:
#
#   * the `mlxfast: packed-scales` certificate line, which only prints when
#     `lagunaHalvedGroup32ScalePlane` certified the plane lossless and
#     `prepareFusedSharedGateUp()` installed it;
#   * the dispatched kernel name, `..._rows1_hs_bf16_v1` for the halved arm and
#     `..._rows1_bf16_v1` for the default, so the two arms are not the same
#     compiled source (standing rule 33);
#   * teacher-forced greedy-token divergences against the public long-copy gate;
#   * a self-fed free-run token hash, which compounds any single-step
#     difference instead of resetting the trajectory every step.
#
#   OUT=/tmp/maple-pr443-correctness bash research/maple_pr443_correctness.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-pr443-correctness}"
STEPS="${STEPS:-128}"
FREERUN_STEPS="${FREERUN_STEPS:-256}"
# The public long-copy gate's own continuation is the period-3 cycle
# 509/902/5991, so self-feeding it is identical to teacher forcing. Feeding a
# different step-0 token opens the trajectory up; its identity is arbitrary and
# shared by every compared arm.
BOOTSTRAP="${BOOTSTRAP:-1}"

mkdir -p "${OUT}"
SUMMARY="${OUT}/summary.txt"
: >"${SUMMARY}"

for arm in off on; do
  halved=""
  [ "${arm}" = "on" ] && halved=1

  log="${OUT}/${arm}-tripwire.log"
  echo "########## ${arm}: ${STEPS}-step teacher-forced tripwire ##########" \
    | tee "${log}"
  env DARKBLOOM_SHARED_SCALE_HALVED="${halved}" \
    python3 research/decode_probe.py --steps "${STEPS}" \
      --stderr "${OUT}/${arm}-tripwire.err" 2>&1 | tee -a "${log}"
  rc="${PIPESTATUS[0]}"
  diverg="$(grep -o 'teacher-forced greedy tokens: [0-9]* divergences' "${log}" \
    | tail -1 | awk '{print $4}')"
  cert="$(grep -h 'packed-scales' "${OUT}/${arm}-tripwire.err" \
    | tr '\n' ';' | sed 's/mlxfast: //g')"
  kernel="$(grep -oh 'laguna_shared_nvfp4_swiglu_qmv_rows1[a-z0-9_]*' \
    "${OUT}/${arm}-tripwire.err" | sort -u | tr '\n' ',')"
  peak="$(grep -oh 'peak_ram_gb[ =:]*[0-9.]*' "${OUT}/${arm}-tripwire.err" \
    "${log}" | tail -1)"
  echo "${arm} tripwire rc=${rc} divergences=${diverg:-NA} ${peak:-peak=NA}" \
    | tee -a "${SUMMARY}"
  echo "${arm} certificate: ${cert:-NONE}" | tee -a "${SUMMARY}"
  echo "${arm} kernels: ${kernel:-NONE}" | tee -a "${SUMMARY}"

  log="${OUT}/${arm}-freerun.log"
  echo "########## ${arm}: ${FREERUN_STEPS}-step self-fed free run ##########" \
    | tee "${log}"
  env DARKBLOOM_SHARED_SCALE_HALVED="${halved}" \
    python3 research/decode_probe.py --steps "${FREERUN_STEPS}" --free-run \
      --free-run-bootstrap "${BOOTSTRAP}" \
      --dump-tokens "${OUT}/${arm}-freerun.tokens" \
      --stderr "${OUT}/${arm}-freerun.err" 2>&1 | tee -a "${log}"
  rc="${PIPESTATUS[0]}"
  hash="$(grep -o 'hash=[0-9a-f]*' "${log}" | tail -1 | cut -d= -f2)"
  echo "${arm} freerun rc=${rc} hash=${hash:-NA}" | tee -a "${SUMMARY}"
done

echo
echo "===== PR #443 correctness summary ====="
cat "${SUMMARY}"
if cmp -s "${OUT}/off-freerun.tokens" "${OUT}/on-freerun.tokens"; then
  echo "free-run token streams: IDENTICAL"
else
  echo "free-run token streams: DIFFER"
fi
