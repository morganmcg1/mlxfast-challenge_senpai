#!/usr/bin/env bash
# Research-only Stage 0 reachability probe for the QKV-GEMV packing curve.
#
#   research/tanjiro_packing_stage0.sh /tmp/tanjiro/stage0 [STEPS]
#
# Requires research/tanjiro_packing_probe.patch applied and the worker rebuilt.
# For each candidate simdgroups-per-threadgroup S it runs a very short decode
# and harvests the `PACKPROBE` stderr lines, which report the *actually encoded*
# grid/threadgroup geometry plus a FALLBACK marker whenever the lane-major
# branch was not the one that ran. An S that only produces FALLBACK lines is
# not a timing arm: the knob never reached the scored kernel.
set -uo pipefail
OUTDIR="${1:?outdir}"
STEPS="${2:-6}"
ARMS="${ARMS:-1 2 4 8 16 32}"
mkdir -p "${OUTDIR}"

for sg in ${ARMS}; do
  echo "=== $(date -u +%H:%M:%S) S=${sg}"
  DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS="${sg}" \
  DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE=0 \
  python3 research/decode_probe.py --steps "${STEPS}" \
    --stderr "${OUTDIR}/s${sg}.err" \
    > "${OUTDIR}/s${sg}.log" 2>&1
  echo "--- exit=$? PACKPROBE lines:"
  grep -h "PACKPROBE" "${OUTDIR}/s${sg}.err" "${OUTDIR}/s${sg}.log" 2>/dev/null | sort -u
  grep -E "^(teacher-forced|decode steps=)" "${OUTDIR}/s${sg}.log" 2>/dev/null
done
echo "=== $(date -u +%H:%M:%S) stage0 done"
