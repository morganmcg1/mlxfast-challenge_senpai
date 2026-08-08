#!/usr/bin/env bash
# Research-only in-situ reachability + token smoke for PR #441.
#
#   research/nezuko_q12_smoke.sh OUTDIR [STEPS]
#
# The bitwise harness (research/nezuko_q12_router_tournament_check.sh) proves the
# two MSL sources agree on synthetic rows, but it dispatches its own kernels and
# therefore says nothing about whether the runtime dispatcher actually selects
# the tournament arm. This runs the real worker on all three arms with
# DARKBLOOM_TRACE_FUSION=1 and reports, per arm:
#
#   * the fusion-trace lines, so "which arm ran" is observed, not assumed;
#   * the teacher-forced greedy divergence count, which must be 0 for every arm.
#
# A tournament run whose stderr lacks "decode router top8 tournament arm=" would
# be a silent fallback to the incumbent, i.e. a null result mislabelled as a win.
set -uo pipefail
OUTDIR="${1:?outdir}"
STEPS="${2:-32}"
mkdir -p "${OUTDIR}"

for spec in off:0 on:1 inert:inert; do
  arm="${spec%%:*}"
  flag="${spec##*:}"
  echo "=== $(date -u +%H:%M:%S) arm=${arm} flag=${flag}"
  DARKBLOOM_TRACE_FUSION=1 DARKBLOOM_DECODE_ROUTER_TOURNAMENT="${flag}" \
  python3 research/decode_probe.py --steps "${STEPS}" \
    --stderr "${OUTDIR}/${arm}.err" \
    > "${OUTDIR}/${arm}.log" 2>&1
  grep -E "^(teacher-forced|decode steps=)" "${OUTDIR}/${arm}.log"
  echo "--- router trace lines:"
  grep -E "fusion active: (decode router|prefill router)" "${OUTDIR}/${arm}.err" \
    || echo "    (none)"
done
echo "=== $(date -u +%H:%M:%S) smoke done"
