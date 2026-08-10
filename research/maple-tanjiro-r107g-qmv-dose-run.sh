#!/bin/bash
# R107-G family D (T2c routed gate/up QMV) dose + bytes ladder driver.
#
# Arm order is fixed by fern's probe contract: a single-file invocation is the
# A/B NULL control (identical MSL in both slots), so the instrument bias floor
# is printed before any candidate number exists.
#
# usage: maple-tanjiro-r107g-qmv-dose-run.sh SESSION [SLOTS]
#   SESSION  label written into the artifact filenames (s1, s2, resident, ...)
#   SLOTS    FERN_DEFEAT_SLOTS; 64 = residency defeated, 1 = resident
#            (a resident session is diagnostic only -- rule 98.9)
set -u
BIN=${BIN:-/tmp/tanjiro_r107g_qmv}
ART=research/artifacts/maple-tanjiro-r107g
SESSION="${1:?session label}"
SLOTS="${2:-64}"
export FERN_DEFEAT_SLOTS="$SLOTS"
export FERN_LADDER=${FERN_LADDER:-128,256,512,1024,2048}
export FERN_ROUNDS=${FERN_ROUNDS:-41}
export FERN_REPS=${FERN_REPS:-200}

null_log="${ART}/stage1-D-null-${SESSION}-slots${SLOTS}.txt"
echo "### NULL CONTROL  session=${SESSION} slots=${SLOTS} ###"
"$BIN" "${ART}/qmv_dose0.metal" > "$null_log" 2>&1
echo "exit=$?  -> ${null_log}"
sed -n '/=== memory regime/,/^$/p' "$null_log"
grep -A3 'NULL(' "$null_log" | head -12

dose_log="${ART}/stage1-D-dose-${SESSION}-slots${SLOTS}.txt"
echo "### DOSE LADDER  session=${SESSION} slots=${SLOTS} ###"
"$BIN" "${ART}/qmv_dose0.metal" "${ART}/qmv_dose4.metal" \
    "${ART}/qmv_dose8.metal" "${ART}/qmv_dose16.metal" > "$dose_log" 2>&1
echo "exit=$?  -> ${dose_log}"
sed -n '/=== pipeline reflection/,/^$/p' "$dose_log"
sed -n '/VERDICT:/p' "$dose_log"
grep -E '^ +(128|256|512|1024|2048) +[0-9]|^--- ' "$dose_log"
