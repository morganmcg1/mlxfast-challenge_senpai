#!/bin/bash
# Research-only: A0 discriminator for the PR #101 vs PR #158 contradiction.
#
# PR #101 measured concurrent-vs-serial encoder dispatch as +0.456 ms/step of
# decode wall time. PR #158 measured gpu_busy_sum flat to +/-0.06 ms/step while
# command buffers per step went 45 -> 204, and concluded hidden concurrent work
# is <= 0.06 ms/step. The two results are 7.6x apart.
#
# The two probes never ran in the same currency. This script reruns #101's
# encoder dispatch-type toggle with the #158 GPUPROF hook applied at the same
# time, so decode step wall, gpu_busy_sum, and the per-kernel breakdown all come
# out of the *same* runs. That is the discriminating measurement.
#
# Requires a worker built with BOTH:
#   research/nezuko-serial-dispatch-probe.patch   (DARKBLOOM_FORCE_SERIAL_DISPATCH)
#   research/nezuko-pr158-gpuprof-hook.patch      (DARKBLOOM_GPU_PROFILE)
set -u
cd "$(dirname "$0")/.."

OUT="${OUT:-research/nezuko-a0-dispatch-type}"
STEPS="${STEPS:-400}"
PY="${PY:-/Users/ec2-user/.senpai/venv/bin/python}"
SETTLE="${SETTLE:-25}"
mkdir -p "$OUT"

thermals() {
  if [ -x "$HOME/bin/macmon" ]; then
    "$HOME/bin/macmon" pipe -s1 2>/dev/null | head -1 \
      | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
    print("thermal gpu_temp=%.1f cpu_temp=%.1f gpu_power=%.2f" % (
        d.get("temp",{}).get("gpu_temp_avg",-1),
        d.get("temp",{}).get("cpu_temp_avg",-1),
        d.get("gpu_power",-1)))
except Exception as e:
    print("thermal unavailable: %s" % e)'
  else
    echo "thermal unavailable: no macmon"
  fi
}

run_point() {
  local tag="$1"; local serial="$2"; local hook="$3"; local split="$4"
  local log="$OUT/$tag.txt"
  echo "=== $tag steps=$STEPS serial=$serial hook=$hook split=$split ==="
  thermals
  local -a envv=(DARKBLOOM_FORCE_SERIAL_DISPATCH="$serial")
  local -a extra=()
  if [ "$hook" = 1 ]; then
    envv+=(DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="$split")
    extra+=(--profile --profile-top 60)
  fi
  env "${envv[@]}" "$PY" research/decode_probe.py --steps "$STEPS" \
      "${extra[@]}" \
      --dump-steps "$OUT/$tag.steps.txt" \
      --stderr "$OUT/$tag.worker.err" >"$log" 2>&1
  echo "exit=$?"
  grep -E 'divergence|^decode steps|^profile:|SERIAL_DISPATCH_PROBE' "$log" | head -6
  grep -m1 SERIAL_DISPATCH_PROBE "$OUT/$tag.worker.err" || echo "WARNING: no probe banner in worker stderr"
  sleep "$SETTLE"
}

# Phases are "<hook>:<split>" specs.
#   1:0  wall + gpu_busy_sum + per-kernel from the same runs (headline).
#   0:0  wall-only confirmation that the delta is not a GPUPROF-hook artifact.
#   1:2  overlap that survives when only adjacent dispatch pairs share a buffer.
#   1:1  control: one dispatch per command buffer leaves no intra-encoder
#        concurrency to remove, so serial-minus-concurrent must be ~0.
ORDER="${ORDER:-A B B A A B B A}"
PHASES="${PHASES:-1:0 0:0}"

for phase in $PHASES; do
  hook="${phase%%:*}"
  split="${phase##*:}"
  i=0
  for cond in $ORDER; do
    i=$((i + 1))
    if [ "$cond" = A ]; then
      run_point "$(printf 'h%sk%s_s%02d_concurrent' "$hook" "$split" "$i")" 0 "$hook" "$split"
    else
      run_point "$(printf 'h%sk%s_s%02d_serial' "$hook" "$split" "$i")" 1 "$hook" "$split"
    fi
  done
done

echo "=== done -> $OUT ==="
