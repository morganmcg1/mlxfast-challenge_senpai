#!/usr/bin/env bash
# Mutation-adequacy driver for research/tanjiro_nax_exec_equiv.swift.
#
# An equivalence test that cannot fail proves nothing. This script builds the
# base kernel, the candidate kernel, and four deliberately mutated candidates,
# then runs every one of them through the byte-comparison harness so the
# harness's own sensitivity is part of the receipt.
#
#   M1  swap the two extracted scale bytes inside the wide-scale window
#   M2  phase mask 3 -> 1 (reload the window every 2 k-iterations)
#   M3  phase stride +1 -> +2
#   M4  force win_ok false, i.e. always take the scalar fallback
#
# M1 and M3 must MISMATCH: that is what proves the widened path actually
# executes on both ranked shapes and really drives the output. M4 must match,
# which shows the fallback arm is equivalent to base. M2 is an *equivalent*
# mutant by construction -- reloading twice as often is still correct -- and is
# kept because a passing M2 is evidence the lane-selection algebra is right for
# every phase, not just the ones the shipped stride visits.
#
# Usage: BASE_REV=<sha> bash research/tanjiro_nax_exec_equiv_mutants.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
BASE_REV="${BASE_REV:?set BASE_REV to the assignment base commit}"
GEN_REL="Vendor/mlx-swift/Source/Cmlx/mlx-generated"
TRIALS="${TRIALS:-3}"

build() { # build <gen_dir> <ws> <out_dir>
  GEN_DIR="$1" BK=64 PROBE=0 PF=0 WS="$2" EMIT_LIB=1 EMIT_IR=1 OUT_DIR="$3" \
    bash research/nax_msl_compile_check.sh >"$3.log" 2>&1
}

echo "== staging base tree ($BASE_REV) =="
rm -rf /tmp/nax_gen_base && mkdir -p /tmp/nax_gen_base
for f in utils gemm_nax quantized_utils fp_quantized_nax; do
  git show "${BASE_REV}:${GEN_REL}/${f}.cpp" > "/tmp/nax_gen_base/${f}.cpp" || exit 1
done
build /tmp/nax_gen_base 0 /tmp/nax_base || { echo "base build FAILED"; exit 1; }
build "${REPO_ROOT}/${GEN_REL}" 1 /tmp/nax_cand || { echo "cand build FAILED"; exit 1; }

echo "== staging mutants =="
for m in m1 m2 m3 m4; do
  rm -rf "/tmp/nax_gen_${m}" && mkdir -p "/tmp/nax_gen_${m}"
  cp "${GEN_REL}"/*.cpp "/tmp/nax_gen_${m}/"
done
F=fp_quantized_nax.cpp
# M1: swap the byte-extraction shifts.
perl -0pi -e 's/sc\[0\] = uint8_t\(lane >> sh\);\n(\s*)sc\[1\] = uint8_t\(lane >> \(sh \+ 8\)\);/sc[0] = uint8_t(lane >> (sh + 8));\n$1sc[1] = uint8_t(lane >> sh);/' "/tmp/nax_gen_m1/$F"
# M2: halve the amortization window.
perl -0pi -e 's/scale_phase \+ 1\) & \(kScaleWinPhases - 1\)/scale_phase + 1) & 1/' "/tmp/nax_gen_m2/$F"
# M3: skip every other phase.
perl -0pi -e 's/\(scale_phase \+ 1\) & \(kScaleWinPhases - 1\)/(scale_phase + 2) \& (kScaleWinPhases - 1)/' "/tmp/nax_gen_m3/$F"
# M4: never take the widened path.
perl -0pi -e 's/const bool win_ok = load_ok &&/const bool win_ok = false \&\& load_ok \&\&/' "/tmp/nax_gen_m4/$F"

for m in m1 m2 m3 m4; do
  if ! grep -q "$( [ "$m" = m4 ] && echo 'win_ok = false' || echo 'scale_phase' )" "/tmp/nax_gen_${m}/$F"; then
    echo "mutant ${m}: patch did not apply"; exit 1
  fi
  build "/tmp/nax_gen_${m}" 1 "/tmp/nax_${m}" || { echo "${m} build FAILED"; exit 1; }
done

run() { TRIALS="${TRIALS}" swift research/tanjiro_nax_exec_equiv.swift \
          /tmp/nax_base/unit.metallib "$1" 2>&1 | grep -E "^EXEC-EQUIV"; }

echo ""
printf '%-6s %-46s %-10s %s\n' ARM MUTATION EXPECT RESULT
fail=0
check() { # check <label> <desc> <expect> <lib>
  got="$(run "$4")"
  case "$got" in *PASS*) v=PASS;; *) v=FAIL;; esac
  printf '%-6s %-46s %-10s %s\n' "$1" "$2" "$3" "$v"
  [ "$v" = "$3" ] || fail=$((fail + 1))
}
check cand "shipped candidate (wide_scale=true)"          PASS /tmp/nax_cand/unit.metallib
check M1   "swap sc[0]/sc[1] in the wide window"          FAIL /tmp/nax_m1/unit.metallib
check M2   "phase mask 3->1 (equivalent by construction)" PASS /tmp/nax_m2/unit.metallib
check M3   "phase stride +1 -> +2"                        FAIL /tmp/nax_m3/unit.metallib
check M4   "win_ok forced false (scalar fallback)"        PASS /tmp/nax_m4/unit.metallib

echo ""
if [ "$fail" -eq 0 ]; then
  echo "MUTATION ADEQUACY: PASS (harness is sensitive; wide path is live)"
else
  echo "MUTATION ADEQUACY: ${fail} arm(s) disagreed with expectation"
fi
exit "$fail"
