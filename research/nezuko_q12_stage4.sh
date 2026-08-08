#!/usr/bin/env bash
# Research-only Stage 4 driver for PR #441: both ORDER directions in one job.
#
#   research/nezuko_q12_stage4.sh ROOT [BLOCKS] [STEPS]
#
# Standing rule 36 wants each arm to visit both slot kinds, which a single
# palindrome cannot do: in "off on inert inert on off" the off arm always owns
# the two outermost slots and inert always owns the two innermost ones. Running
# the reversed palindrome second gives every arm both roles, and
# research/nezuko_q12_stats.py renumbers the second direction's blocks into a
# disjoint range so the block dummies absorb any order effect.
set -uo pipefail
ROOT="${1:?root outdir}"
BLOCKS="${2:-4}"
STEPS="${3:-256}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${HERE}/nezuko_q12_abba.sh" "${ROOT}/orderA" "${BLOCKS}" "${STEPS}" \
  "off on inert inert on off"
bash "${HERE}/nezuko_q12_abba.sh" "${ROOT}/orderB" "${BLOCKS}" "${STEPS}" \
  "inert on off off on inert"
echo "=== $(date -u +%H:%M:%S) stage 4 complete"
