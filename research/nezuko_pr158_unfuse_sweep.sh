#!/usr/bin/env bash
# Research-only (PR #158): dispatch-count regression for the decode gap.
#
# The MLX_MAX_MB_PER_BUFFER sweep varies command buffers per step while holding
# dispatches per step at 406, which separates a per-command-buffer cost from the
# rest but cannot tell a per-dispatch host cost apart from a per-step fixed one.
#
# Every DARKBLOOM_FUSED_* flag here is default-on and ablates to a longer kernel
# chain computing the same thing, so setting one to 0 raises dispatches/step
# without changing the number of decode steps or the IPC protocol. Regressing
# gap = wall - gpu_busy_sum against (dispatches, cbs) across these arms
# attributes the ~235 us CB-independent residual.
#
# Ablation arms are diagnostic only: they are slower and some may not be
# bit-exact. The probe reports token divergences per arm so an arm that changes
# results is visible rather than silent.
set -uo pipefail
cd "$(dirname "$0")/.."

STEPS="${STEPS:-200}"
OUT="${OUT:-research/nezuko-pr158-unfuse-sweep.log}"
: >"$OUT"

thermal() {
  "$HOME/bin/macmon" pipe -s1 2>/dev/null \
    | jq -c '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
    2>/dev/null || echo '{}'
}

ARMS="${ARMS:-base:  rrr:DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER=0 rsdr:DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL=0 ssq:DARKBLOOM_FUSED_SHARED_SWIGLU_QMV=0 rsq:DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV=0 base2:}"

for arm in $ARMS; do
  name="${arm%%:*}"
  kv="${arm#*:}"
  tag="$name-$(date +%H%M%S)"
  echo "=== arm=$name env='$kv' tag=$tag t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
  env ${kv:+"$kv"} DARKBLOOM_GPU_PROFILE=1 \
    python3 research/nezuko_pr158_gap_probe.py \
    --steps "$STEPS" --pings 6 --profile --profile-top 6 \
    --label "$tag" --stderr "/tmp/nezuko-pr158-$tag.err" 2>&1 | tee -a "$OUT"
  echo "=== arm=$name done t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
done

echo "=== log -> $OUT"
grep -E "^=== arm|SUMMARY|per steady step|divergences" "$OUT"
