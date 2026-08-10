#!/usr/bin/env bash
# maple-nezuko / r106-B / Stage B finalisation chain.
#
# One supervised job that performs every remaining *measurement* step in the
# order the preregistration requires, so that the evidence campaign, its
# provenance audit, its statistics and its correctness oracle all land from a
# single tree state and a single wake.
#
#   1. block until the paired campaign process exits AND the evidence sink holds
#      the preregistered number of rows;
#   2. re-derive every row from its own run log (kernel name, correctness flag,
#      decode figure) and hard-fail on any disagreement -- Rule 33 provenance;
#   3. compute the primary dof-5 paired contrasts plus the position audit;
#   4. run the zero-tolerance upstream-equivalence oracle for arms off/on/h4.
#
# Steps 2-4 are independent of one another: a failure in one is reported and the
# chain continues, so that a single wake carries the complete picture rather than
# the first problem. The exit code is non-zero if any step failed.
#
# Step 4 rebuilds the tree and touches Package.resolved, so it needs a mutable
# workspace. The paired campaign itself holds the runtime's single mutable slot
# until it exits, so this script can be started in read-only mode with
# SKIP_EXACT=1 for steps 1-3 and step 4 launched separately once the slot frees.
#
# usage: [SKIP_EXACT=1] maple-nezuko-r106b-finalise.sh <campaign_pid> <evidence.tsv> <expected_rows>
set -uo pipefail

PID="${1:?campaign pid}"
SINK="${2:?evidence tsv}"
WANT="${3:?expected data rows}"
SKIP_EXACT="${SKIP_EXACT:-0}"

OUT=/tmp/r106b-finalise
mkdir -p "$OUT"
rc_total=0

say() { printf '[finalise %s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }

# ---- 1. block on the campaign -------------------------------------------------
say "waiting for campaign pid $PID and $WANT rows in $SINK"
while kill -0 "$PID" 2>/dev/null; do
  sleep 10
done
say "campaign pid $PID has exited"

# The runner appends a row only after a run completes, so give the final append
# a moment to land, then require the preregistered row count.
for _ in $(seq 1 30); do
  rows=$(( $(wc -l < "$SINK") - 1 ))
  [ "$rows" -ge "$WANT" ] && break
  sleep 2
done
rows=$(( $(wc -l < "$SINK") - 1 ))
say "evidence rows = $rows (expected $WANT)"
if [ "$rows" -ne "$WANT" ]; then
  say "FATAL: row count mismatch -- the campaign did not complete its design"
  rc_total=1
fi
cp "$SINK" "$OUT/evidence.tsv"

# ---- 2. provenance / row verification ----------------------------------------
say "step 2: verifying every evidence row against its own log"
if bash research/maple-nezuko-r106b-verify-evidence-rows.sh "$SINK" \
     > "$OUT/verify.txt" 2>&1; then
  say "step 2 OK -- $(tail -1 "$OUT/verify.txt")"
else
  say "step 2 FAILED -- see $OUT/verify.txt"
  rc_total=1
fi

# ---- 3. primary statistics + position audit ----------------------------------
say "step 3: primary paired contrasts and position audit"
if python3 research/maple-nezuko-r106b-position-audit.py "$SINK" \
     > "$OUT/audit.txt" 2>&1; then
  say "step 3 OK -- $OUT/audit.txt"
else
  say "step 3 FAILED -- see $OUT/audit.txt"
  rc_total=1
fi

# ---- 4. zero-tolerance exactness oracle --------------------------------------
if [ "$SKIP_EXACT" = "1" ]; then
  say "step 4 SKIPPED (SKIP_EXACT=1); run it separately in a mutable workspace"
else
  say "step 4: upstream-equivalence oracle for arms off/on/h4 (zero tolerance)"
  if bash research/maple-nezuko-r106b-packred-exactness.sh \
       > "$OUT/exactness.txt" 2>&1; then
    say "step 4 OK -- $(grep -c EQUIVALENCE_EXIT "$OUT/exactness.txt") arms reported"
  else
    say "step 4 FAILED -- see $OUT/exactness.txt"
    rc_total=1
  fi
fi

say "finalisation chain done, rc=$rc_total"
exit "$rc_total"
