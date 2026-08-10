#!/usr/bin/env bash
# R107-J: post-hoc, third-party-runnable identity verifier for a certify session.
#
# WHY THIS EXISTS
# The certify harness (research/maple-nezuko-r107j-certify.sh) keeps every raw
# score.json when KEEP=1.  A paired decode CI is only worth the paper it is
# printed on if the two arms really were the SAME harness, the SAME weights and
# the SAME measurement mode -- otherwise the "difference" is a difference of
# instruments, not of code.  This script re-derives those facts from the raw
# JSON, so a reader who does not trust my TSV can check the claim themselves.
#
# It checks, over all kept score files of one session:
#   1. runtime == "swift-local-submit" for EVERY run.  This is the machine-
#      checkable form of guard rail 1: `--local-iterate` stamps a different
#      runtime, so a single mixed run fails the whole session (rule 86).
#   2. checked_steps is the census count and is identical across runs (a short
#      run is a different estimand, not a noisy one).
#   3. harness_hash is identical across runs (same scorer).
#   4. weights_hash is identical across runs (same model bytes).
#   5. commit is identical across runs (the numbers describe ONE tree).
#   6. golden_hash: reported per distinct value with counts.  For an A/A null
#      there must be exactly one.  For a not-bit-exact candidate arm there will
#      be two, and that is a finding to report, not an error to hide.
#   7. passed_correctness: reported per distinct value with counts.
#
# Usage:
#   research/maple-nezuko-r107j-verify-identity.sh <SESSION>
#   research/maple-nezuko-r107j-verify-identity.sh /tmp/r107j_20260810T153224Z_*.score.json
# With a bare SESSION id it globs /tmp/r107j_<SESSION>_*.score.json.
#
# Exit 0 = every invariant held.  Exit 1 = at least one invariant broke.
set -uo pipefail

command -v jq >/dev/null || { echo "FATAL: jq is required" >&2; exit 2; }

declare -a FILES=()
if [[ $# -eq 1 && "$1" != *.json ]]; then
  while IFS= read -r f; do FILES+=("$f"); done \
    < <(ls -1 /tmp/r107j_"$1"_*.score.json 2>/dev/null | sort)
else
  FILES=("$@")
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "FATAL: no score files selected" >&2
  exit 2
fi

echo "=== r107j identity verifier: ${#FILES[@]} score file(s)"
FAIL=0

field() { jq -r "$2" "$1" 2>/dev/null; }

# --- invariant 1: every run is a --local-submit census run -------------------
bad=0
for f in "${FILES[@]}"; do
  rt="$(field "$f" '.metrics.runtime')"
  if [[ "$rt" != "swift-local-submit" ]]; then
    echo "  FAIL runtime='${rt}' (expected swift-local-submit) in ${f}"
    bad=1
  fi
done
if [[ $bad -eq 0 ]]; then
  echo "  OK   [1] runtime == swift-local-submit in all ${#FILES[@]} runs"
  echo "       (guard rail 1 holds: no --local-iterate contamination, rule 86)"
else
  FAIL=1
fi

# --- invariants 2-5: single-valued session identity -------------------------
check_single() {
  local label="$1" expr="$2" want="${3:-}"
  local vals n
  vals="$(for f in "${FILES[@]}"; do field "$f" "$expr"; done | sort -u)"
  n="$(printf '%s\n' "$vals" | grep -c . )"
  if [[ "$n" -ne 1 ]]; then
    echo "  FAIL [${label}] ${n} distinct values across the session:"
    printf '         %s\n' $vals
    FAIL=1
    return
  fi
  if [[ -n "$want" && "$vals" != "$want" ]]; then
    echo "  FAIL [${label}] = ${vals} (expected ${want})"
    FAIL=1
    return
  fi
  echo "  OK   [${label}] single-valued: ${vals}"
}

check_single "2 checked_steps" '.metrics.checked_steps'
check_single "3 harness_hash"  '.metrics.harness_hash'
check_single "4 weights_hash"  '.metrics.weights_hash'
check_single "5 commit"        '.metrics.commit'

# --- invariants 6-7: reported, not enforced --------------------------------
report_multi() {
  local label="$1" expr="$2"
  echo "  --   [${label}] distinct values (count value):"
  for f in "${FILES[@]}"; do field "$f" "$expr"; done | sort | uniq -c \
    | sed 's/^/         /'
}
report_multi "6 golden_hash"        '.metrics.golden_hash'
report_multi "7 passed_correctness" '.metrics.passed_correctness'

# --- prefill neutrality context (rule 105.4) -------------------------------
echo "  --   [8] prefill_seconds_per_token spread (rule 105.4: prefill is"
echo "         charged neutral -- it must not differ systematically by arm):"
for f in "${FILES[@]}"; do field "$f" '.metrics.prefill_seconds_per_token'; done \
  | sort -n | awk 'NR==1{min=$1} {a[NR]=$1; s+=$1} END{
      printf "         n=%d min=%.9f max=%.9f mean=%.9f\n", NR, min, a[NR], s/NR}'

echo
if [[ $FAIL -eq 0 ]]; then
  echo "VERDICT: PASS -- every arm of this session is the same instrument."
else
  echo "VERDICT: FAIL -- the arms are NOT the same instrument; the paired CI"
  echo "         from this session must not be quoted as evidence."
fi
exit $FAIL
