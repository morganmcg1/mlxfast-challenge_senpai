#!/bin/bash
# PR #80 counterbalanced PREFILL ABBA.
#
# WHY THIS EXISTS
# ---------------
# The matched pair in the report's 6.6 measured prefill +0.931% on the
# candidate (n=1/arm, uncounterbalanced). Priced against the ranked window
# that is -0.338% of score, which would eat half the +0.633% byte gain, so it
# has to be resolved rather than waved away.
#
# WHAT STATIC ANALYSIS ALREADY SETTLES
# ------------------------------------
# Neither mechanism in this PR is reachable at L=512:
#
#   o_proj  lagunaGatedAffineOProjNVFP4 is called only from inside the `if`
#           at LagunaRuntimeModel.swift:6139, whose guard at :6140 requires
#           `B == 1, L == 1`. (At the f2fedd58 base the same call sites are
#           :6160/:6176 under the identical guard at :6114 -- these are the
#           anchors :6165/:6181 that carry `narrowScales:`.)
#   QKV     lagunaDecodeNVFP4QKVR1 has exactly one caller, :5761, nested in
#           the `B == 1, L == 1` guard at :5704-5705.
#
# So the candidate and the base issue the SAME kernels, with the SAME
# arguments, for every one of the 512 prefill rows. The predicted prefill
# effect is exactly zero, and the -0.338% meridian priced has no mechanism.
#
# WHAT IS LEFT TO TEST, AND WHAT THIS SCRIPT TESTS
# ------------------------------------------------
# One second-order channel survives the static argument: building the
# lane-major bank leaves ~23.5 MB of extra arrays resident, which could in
# principle perturb prefill through allocator or residency pressure. That is
# exactly the variable `DARKBLOOM_ATTN_SCALE_NARROW_OPROJ` controls, because
# it gates the bank CONSTRUCTION at LagunaRuntimeModel.swift:5483-5488, not
# any dispatch:
#
#   D = shipped default            o_proj lane-major+pairwise bank built
#   S = ..._NARROW_OPROJ=0         bank not built; stock plane resident only
#
# Both arms come from ONE binary, so no rebuild confound. A null result here
# plus the static proof above closes the prefill question completely; a real
# S-vs-D split at L=512 would mean the cost is residency, not compute, and
# would need a different fix from the one meridian priced.
#
# Position balance: discard, then D S S D D S S D (each arm's positions sum 18).
set -u
cd "$(dirname "$0")/.."

REPS="${PR80_PREFILL_REPS:-20}"
WARM="${PR80_PREFILL_WARM:-4}"
LEN="${PR80_PREFILL_LEN:-512}"

MACMON="${HOME}/bin/macmon"
thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_temp:.temp.gpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

run_arm() {
  local pos="$1" arm="$2"
  local envs=""
  if [ "${arm}" = "S" ]; then
    envs="DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0"
  fi
  echo "=== ${pos} arm=${arm} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  # shellcheck disable=SC2086
  /usr/bin/env ${envs} \
    python3 research/frieren_host_cpu_probe.py \
      --mode prefill --seed-tokens "${LEN}" \
      --warmup-steps "${WARM}" --measure-steps "${REPS}" \
      --label "${pos}-${arm}" 2>/dev/null
}

run_arm p00-discard D
for spec in "p01 D" "p02 S" "p03 S" "p04 D" \
            "p05 D" "p06 S" "p07 S" "p08 D"; do
  # shellcheck disable=SC2086
  run_arm ${spec}
done
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
