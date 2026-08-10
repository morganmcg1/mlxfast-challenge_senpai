#!/bin/bash
# R109-C stage 0(b): extract-round prologue ceiling on the routed gate/up QMV.
#
# The NULL control runs first (one file => identical MSL in both slots), so the
# instrument's bias floor is on record before any candidate number exists.
#
# usage: maple-tanjiro-r109c-ceiling-run.sh SESSION [SLOTS]
#   SESSION  label written into the artifact filenames (s1, s2, resident, ...)
#   SLOTS    FERN_DEFEAT_SLOTS; 64 = residency defeated (headline), 1 = resident
set -u
BIN=${BIN:-/tmp/tanjiro_r109c}
ART=research/artifacts/maple-tanjiro-r109c
SESSION="${1:?session label}"
SLOTS="${2:-64}"
export FERN_DEFEAT_SLOTS="$SLOTS"
export FERN_LADDER=${FERN_LADDER:-128,256,512,1024,2048}
export FERN_ROUNDS=${FERN_ROUNDS:-41}
export FERN_REPS=${FERN_REPS:-200}

null_log="${ART}/null-${SESSION}-slots${SLOTS}.txt"
echo "### NULL CONTROL  session=${SESSION} slots=${SLOTS} ###"
"$BIN" "${ART}/A_base.metal" > "$null_log" 2>&1
echo "exit=$?  -> ${null_log}"
grep -E '^ +(128|256|512|1024|2048) +[0-9]|^--- |VERDICT:' "$null_log"

ab_log="${ART}/ceiling-${SESSION}-slots${SLOTS}.txt"
echo "### A/B CEILING  session=${SESSION} slots=${SLOTS} ###"
"$BIN" "${ART}/A_base.metal" "${ART}/B_inds.metal" "${ART}/C_sg0.metal" > "$ab_log" 2>&1
echo "exit=$?  -> ${ab_log}"
sed -n '/=== pipeline reflection/,/^$/p' "$ab_log"
sed -n '/=== output equivalence/,/^$/p' "$ab_log"
sed -n '/=== memory regime/,/^$/p' "$ab_log"
grep -E '^ +(128|256|512|1024|2048) +[0-9]|^--- ' "$ab_log"
