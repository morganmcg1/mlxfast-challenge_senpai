#!/usr/bin/env bash
# Research-only (PR #158): does the decode host gap scale with GPU busy time?
#
# The earlier SPLIT and single-flag UNFUSE sweeps moved gpu_busy_sum over only
# 7.93-8.47 ms (6.8%). A perfectly proportional gap would move ~17 us across
# that range, which is the gap's own replicate scatter, so those data cannot
# separate "absolute host cost" from "proportional to GPU work". This sweep
# widens the busy lever to ~25% with a 2x2 design:
#
#   seed lever   512 -> 32 tokens: shrinks attention KV work only. Dispatch and
#                command-buffer counts per step are unchanged, so it is a clean
#                busy-only lever with no host-side confound. Timing-only: the
#                arm free-runs greedily instead of teacher-forcing.
#   unfuse lever all four DARKBLOOM_FUSED_* flags off at once: raises busy
#                ~+15% but also raises dispatches 406 -> ~874, so it carries a
#                host confound the seed lever does not.
#
# Crossing them lets one regression separate the busy coefficient from the
# dispatch coefficient. Order is ABBA-style so host/thermal drift cancels.
set -uo pipefail
cd "$(dirname "$0")/.."

STEPS="${STEPS:-200}"
OUT="${OUT:-research/nezuko-pr158-busy-range-sweep.log}"
: >"$OUT"

UNFUSE4="DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER=0 DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL=0 DARKBLOOM_FUSED_SHARED_SWIGLU_QMV=0 DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV=0"

thermal() {
  "$HOME/bin/macmon" pipe -s1 2>/dev/null \
    | jq -c '{cpu_temp:.temp.cpu_temp_avg,gpu_pw:.gpu_power,ram_pw:.ram_power}' \
    2>/dev/null || echo '{}'
}

run_arm() {
  local name="$1" seed="$2" unfuse="$3"
  local tag="$name-$(date +%H%M%S)"
  local envs="DARKBLOOM_GPU_PROFILE=1"
  [ "$unfuse" = "1" ] && envs="$envs $UNFUSE4"
  echo "=== arm=$name seed=$seed unfuse=$unfuse tag=$tag t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
  env $envs \
    python3 research/nezuko_pr158_gap_probe.py \
    --steps "$STEPS" --pings 6 --profile --profile-top 4 \
    --seed "$seed" --label "$tag" \
    --stderr "/tmp/nezuko-pr158-$tag.err" 2>&1 | tee -a "$OUT"
  echo "=== arm=$name done t=$(date +%H:%M:%S) thermal=$(thermal)" | tee -a "$OUT"
}

# a = base, b = short seed, c = unfused, d = unfused + short seed.
run_arm a1 0 0
run_arm b1 32 0
run_arm c1 0 1
run_arm d1 32 1
run_arm d2 32 1
run_arm c2 0 1
run_arm b2 32 0
run_arm a2 0 0

echo "=== log -> $OUT"
grep -E "^=== arm|SUMMARY|per steady step|divergences|free-run" "$OUT"
