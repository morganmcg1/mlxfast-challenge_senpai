#!/usr/bin/env bash
# Research-only decode dispatch census for the compiled-elementwise-fusion probe.
#
#   bash research/nezuko_compile_census.sh <outdir>
#
# Requires research/nezuko-pr158-gpuprof-hook.patch applied and the worker
# rebuilt. The hook inflates absolute time, so this run is for dispatch
# attribution only; never read its wall clock as timing evidence.
set -uo pipefail

OUTDIR="${1:?outdir}"
mkdir -p "${OUTDIR}"
export DARKBLOOM_GPU_PROFILE=1

census() {
  local tag="$1"
  python3 research/decode_probe.py --steps 60 --profile --profile-top 60 \
    --stderr "${OUTDIR}/${tag}.err" >"${OUTDIR}/${tag}.txt" 2>&1
  echo "--- ${tag} ---"
  grep -E "kernels=|us/step|n/step" -m 2 "${OUTDIR}/${tag}.txt" | head -3
}

(unset DARKBLOOM_FUSED_ROUTER DARKBLOOM_COMPILED_ROUTER_TAIL; census base)
(export DARKBLOOM_FUSED_ROUTER=0 DARKBLOOM_COMPILED_ROUTER_TAIL=0; census unfused)
(export DARKBLOOM_FUSED_ROUTER=0 DARKBLOOM_COMPILED_ROUTER_TAIL=1; census compiled)
