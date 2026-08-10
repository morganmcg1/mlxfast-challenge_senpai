#!/bin/bash
# R105-C A6: measure the OFF-side dispatch count and threadgroup geometry for the
# three gates that have a named "threadgroup underfill" mechanism. The tracer
# records grid and threadgroup dimensions per dispatch, so the OFF column of the
# A6 table is measured rather than inferred from source.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
S="${HERE}/fern_r105c_trace_arm.sh"
chmod +x "$S"
export STEP="${STEP:-5}"

"$S" h_full_attn_off       DARKBLOOM_FUSED_FULL_ATTN=0
"$S" i_sliding_attn_off    DARKBLOOM_FUSED_SLIDING_ATTN=0
"$S" j_residual_rms_router_off DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER=0
echo ALLDONE
