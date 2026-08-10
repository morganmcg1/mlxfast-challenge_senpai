#!/bin/bash
# R105-C A2 positive controls. Without these, an identical dispatch trace is
# unfalsifiable: it cannot be distinguished from "the DARKBLOOM_* variable never
# reached the sandboxed worker". Both arms flip a gate whose OFF branch dispatches
# a structurally different kernel set, so a changed trace proves the plumbing.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
S="${HERE}/fern_r105c_trace_arm.sh"
chmod +x "$S"
export STEP="${STEP:-5}"

"$S" f_fused_scatter_off   DARKBLOOM_ROUTE_FUSED_SCATTER=0
"$S" g_counting_sort_off   DARKBLOOM_ROUTE_COUNTING_SORT=0
echo ALLDONE
