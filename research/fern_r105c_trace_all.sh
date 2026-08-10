#!/bin/bash
# R105-C A2: sequential traced arms (one model-holding process at a time).
# a_base / b_base are the A/A tracer-determinism control; the remaining arms
# each flip exactly one default-ON gate off.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
S="${HERE}/fern_r105c_trace_arm.sh"
chmod +x "$S"
export STEP="${STEP:-5}"

"$S" a_base
"$S" b_base
"$S" c_inverse_scatter_off  DARKBLOOM_INVERSE_SCATTER=0
"$S" d_routed_down_reduce_off DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE=0
"$S" e_shared_down_residual_off DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL=0
echo ALLDONE
