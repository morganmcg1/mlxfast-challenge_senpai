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
# HOOK=0 drops DARKBLOOM_GPU_PROFILE and --profile so the arm is timed in wall
# currency by the unmodified dispatch path. Busy currency needs the hook; wall
# currency must not assume the hook is free.
HOOK="${HOOK:-1}"
# PASSES>1 replays the arm list; PALINDROME=1 reverses every even pass so a
# monotone thermal or clock drift cancels between an arm's two placements.
PASSES="${PASSES:-1}"
PALINDROME="${PALINDROME:-1}"
: >"$OUT"

thermal() {
  "$HOME/bin/macmon" pipe -s1 2>/dev/null \
    | jq -c '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
    2>/dev/null || echo '{}'
}

ARMS="${ARMS:-base:  rrr:DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER=0 rsdr:DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL=0 ssq:DARKBLOOM_FUSED_SHARED_SWIGLU_QMV=0 rsq:DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV=0 base2:}"

run_arm() {
  local arm="$1" pass="$2"
  local name="${arm%%:*}"
  local kv="${arm#*:}"
  local tag="$name-p$pass-$(date +%H%M%S)"
  echo "=== arm=$name pass=$pass env='$kv' hook=$HOOK tag=$tag t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
  if [ "$HOOK" = "1" ]; then
    env ${kv:+"$kv"} DARKBLOOM_GPU_PROFILE=1 \
      python3 research/nezuko_pr158_gap_probe.py \
      --steps "$STEPS" --pings 6 --profile --profile-top 6 \
      --label "$tag" --stderr "/tmp/nezuko-pr158-$tag.err" 2>&1 | tee -a "$OUT"
  else
    env ${kv:+"$kv"} \
      python3 research/nezuko_pr158_gap_probe.py \
      --steps "$STEPS" --pings 6 \
      --label "$tag" --stderr "/tmp/nezuko-pr158-$tag.err" 2>&1 | tee -a "$OUT"
  fi
  echo "=== arm=$name pass=$pass done t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
}

for pass in $(seq 1 "$PASSES"); do
  order="$ARMS"
  if [ "$PALINDROME" = "1" ] && [ $((pass % 2)) -eq 0 ]; then
    order="$(printf '%s\n' $ARMS | tail -r | tr '\n' ' ')"
  fi
  for arm in $order; do
    run_arm "$arm" "$pass"
  done
done

echo "=== log -> $OUT"
grep -E "^=== arm|SUMMARY|per steady step|divergences" "$OUT"
