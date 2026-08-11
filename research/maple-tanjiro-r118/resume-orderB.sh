#!/usr/bin/env bash
# R118-A: finish order B.
#
# The first attempt at the campaign was launched as one supervised job with a
# wall-clock deadline and the deadline fired at 05:16:05Z, mid-run-23 of order B,
# after order A (40/40) and the control block (24/24) had completed.  Runs 1..22
# of order B are on disk and are untouched by this script; run 23 left a .log and
# a .err but no .steps, so no partial row entered the data.
#
# This resumes the SAME pre-registered ORDER_B string from position 23, with the
# run-index offset so the files land in the same directory under the names the
# analyser expects.  Nothing about the order is re-drawn: the arms and their
# positions are exactly the ones frozen in run-r118a.sh at b0d6bec0, 04:12:49Z.
#
# The honest cost of the interruption is a ~10 minute gap in the middle of order
# B's session, between run 22 and run 23.  That is recorded in HOST-HYGIENE.md.
# It does not touch the block contrast (each block is still four runs within a
# few minutes of each other) and it does not touch order B's mirror property
# (the arm sequence is unchanged).
set -u
cd "$(dirname "$0")/../.."

ORDER_B=2301231020312013312002313021312031022031
DONE=22
STEPS="${1:-160}"
OUT=research/maple-tanjiro-r118/evidence/orderB

echo "##### R118-A orderB resume from run $((DONE+1)) t=$(date -u +%H:%M:%S)"
echo "##### full   ORDER_B = ${ORDER_B}"
echo "##### already done   = ${ORDER_B:0:${DONE}}"
echo "##### resuming with  = ${ORDER_B:${DONE}}"
bash research/maple-tanjiro-r118/qmv-dose-abba.sh \
  "${ORDER_B:${DONE}}" "${OUT}" "${STEPS}" "${DONE}"
echo "##### orderB complete t=$(date -u +%H:%M:%S)"
ls "${OUT}"/*.steps | wc -l
