#!/usr/bin/env bash
# Research-only (PR #443): Stage 0 reachability trace plus the equivalence
# oracle, in one model-serialised pass.
#
# `DARKBLOOM_TRACE_FUSION=1` prints one stderr line the first time each fused
# decode path is taken. The shared gate/up QMV has two possible callers --
# `LagunaRuntimeMLP.callAsFunction` (traced "shared gate/up QMV + SwiGLU") and
# `LagunaRuntimeMLP.fusedSharedDownInputs` reached from the fused shared-down
# residual (traced "shared down residual") or from the routed+shared fused
# residual (traced "routed+shared down residual"). PR #301 needed commit
# a15af484 to fix having instrumented the wrong one, so which traces fire is
# recorded here rather than inferred.
#
#   OUT=/tmp/maple-pr443-stage0 bash research/maple_pr443_stage0_trace.sh
set -uo pipefail

OUT="${OUT:-/tmp/maple-pr443-stage0}"
STEPS="${STEPS:-16}"
mkdir -p "${OUT}"
SUMMARY="${OUT}/summary.txt"
: >"${SUMMARY}"

for arm in off on; do
  halved=""
  [ "${arm}" = "on" ] && halved="1"
  log="${OUT}/${arm}-trace.log"
  echo "########## ${arm}: fusion trace ##########" | tee "${log}"
  env DARKBLOOM_TRACE_FUSION=1 DARKBLOOM_SHARED_SCALE_HALVED="${halved}" \
    python3 research/decode_probe.py --steps "${STEPS}" \
      --stderr "${OUT}/${arm}-trace.err" 2>&1 | tee -a "${log}"
  echo "--- ${arm} fusion traces ---" | tee -a "${SUMMARY}"
  grep "fusion active" "${OUT}/${arm}-trace.err" | tee -a "${SUMMARY}"
done

echo "########## upstream equivalence oracle ##########" | tee -a "${SUMMARY}"
bash research/run_upstream_equivalence.sh >"${OUT}/equivalence.log" 2>&1
echo "equivalence rc=$?" | tee -a "${SUMMARY}"
grep -Eo 'maximumAbsoluteLogitError" : [0-9.e-]+|promptTokenCount|Executed [0-9]+ test[s]?' \
  "${OUT}/equivalence.log" | sort | uniq -c | tee -a "${SUMMARY}"
git checkout -- Package.resolved 2>/dev/null || true

echo
echo "===== PR #443 Stage 0 summary ====="
cat "${SUMMARY}"
