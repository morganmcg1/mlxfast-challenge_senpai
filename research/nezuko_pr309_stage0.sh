#!/usr/bin/env bash
# Research-only Stage 0 probe for PR #309 (persistent grid-stride QKV).
#
#   research/nezuko_pr309_stage0.sh /tmp/nez309/stage0
#
# For every arm of the campaign it records:
#   * the encoded threadgroup geometry for both head counts (h64 sliding,
#     h48 full) from DARKBLOOM_DECODE_NVFP4_QKV_GEOMETRY_LOG;
#   * the runtime dispatch tally from DARKBLOOM_ATTN_SCALE_NARROW_LOG, which
#     proves the lane-major kernel is the one that actually ran;
#   * the public 64-step drift tripwire verdict.
# It then runs the two negative controls: the T=256 divisibility hard-fail and
# the injected row-map fault.
set -uo pipefail
OUTDIR="${1:?outdir}"
STEPS="${2:-6}"
mkdir -p "${OUTDIR}"

probe() {
  local tag="$1" sg="$2" nf="$3" tg="$4" fault="${5:-0}"
  echo "=== $(date -u +%H:%M:%S) ${tag} sg=${sg} nf=${nf} tg=${tg} fault=${fault}"
  DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS="${sg}" \
  DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE="${nf}" \
  DARKBLOOM_DECODE_NVFP4_QKV_TOTAL_THREADGROUPS="${tg}" \
  DARKBLOOM_DECODE_NVFP4_QKV_ROW_FAULT="${fault}" \
  DARKBLOOM_DECODE_NVFP4_QKV_GEOMETRY_LOG=1 \
  DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 \
  python3 research/decode_probe.py --steps "${STEPS}" \
    --stderr "${OUTDIR}/${tag}.err" > "${OUTDIR}/${tag}.log" 2>&1
  echo "exit=$?"
  grep -h "qkv-geometry" "${OUTDIR}/${tag}.err" "${OUTDIR}/${tag}.log" 2>/dev/null | sort -u
  grep -hiE "lane-major|narrow-scale|dispatch" "${OUTDIR}/${tag}.err" 2>/dev/null | sort | uniq -c | head
  grep -E "^(teacher-forced|decode steps=)" "${OUTDIR}/${tag}.log" 2>/dev/null
}

for spec in "a0:2:0:0" "G640:16:0:0" "R640:16:3:0" "N640:16:1:0" \
            "G128:16:0:128" "R128:16:3:128" "N128:16:1:128"; do
  IFS=: read -r tag sg nf tg <<<"${spec}"
  probe "${tag}" "${sg}" "${nf}" "${tg}"
done

echo "=== negative control: T=256 is not an exact divisor of h64 rows (10240)"
probe "neg_tg256" 16 1 256

echo "=== negative control: injected row-map fault at the winning geometry"
probe "neg_fault" 16 1 128 1
echo "=== $(date -u +%H:%M:%S) stage0 done"
