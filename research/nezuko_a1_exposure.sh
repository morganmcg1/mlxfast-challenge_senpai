#!/bin/bash
# Research-only: A1 exposure factors E = dS/dI for default-ON decode knobs.
#
# dI ("isolated cost delta") is the change in the SPLIT=1 per-kernel census sum
# when the knob is turned off. At SPLIT=1 every dispatch owns a command buffer,
# so no dispatch overlaps any other and each kernel is timed in isolation. The
# per-command-buffer overhead is identical in both arms and cancels in the
# difference.
#
# dS ("step delta") is the change in decode step wall time with the GPUPROF hook
# off, i.e. the currency the score is actually paid in.
#
# E = dS / dI is then the fraction of a kernel's isolated cost that is exposed to
# the step. E ~ 1 means the kernel is on the critical path; E ~ 0 means it is
# already hidden underneath a sibling dispatch and making it faster buys nothing.
#
# Requires a worker built with research/nezuko-pr158-gpuprof-hook.patch.
set -u
cd "$(dirname "$0")/.."

OUT="${OUT:-research/nezuko-a1-exposure}"
PY="${PY:-/Users/ec2-user/.senpai/venv/bin/python}"
SETTLE="${SETTLE:-25}"
WALL_STEPS="${WALL_STEPS:-400}"
CENSUS_STEPS="${CENSUS_STEPS:-200}"
# ABBA over {knob ON, knob OFF}. ON is the shipped default.
WALL_ORDER="${WALL_ORDER:-A B B A A B B A}"
CENSUS_ORDER="${CENSUS_ORDER:-A B B A}"
KNOBS="${KNOBS:-DARKBLOOM_ROUTED_GATEUP_R1 DARKBLOOM_SHARED_QMV_R1}"
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

# run_point <tag> <knob> <knobval> <hook> <split> <steps>
run_point() {
  local tag="$1"; local knob="$2"; local knobval="$3"
  local hook="$4"; local split="$5"; local steps="$6"
  local log="$OUT/$tag.txt"
  echo "=== $tag knob=$knob=$knobval hook=$hook split=$split steps=$steps ==="
  mkdir -p "$OUT"
  thermals
  local -a envv=("$knob=$knobval")
  local -a extra=()
  if [ "$hook" = 1 ]; then
    envv+=(DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT="$split")
    extra+=(--profile --profile-top 200)
  fi
  # bash 3.2 (macOS) treats "${extra[@]}" as unbound under `set -u` when empty.
  env "${envv[@]}" "$PY" research/decode_probe.py --steps "$steps" \
      ${extra[@]+"${extra[@]}"} \
      --dump-steps "$OUT/$tag.steps.txt" \
      --stderr "$OUT/$tag.worker.err" >"$log" 2>&1
  echo "exit=$?"
  grep -E 'divergence|^decode steps|^profile:' "$log" | head -4
  sleep "$SETTLE"
}

for knob in $KNOBS; do
  short="$(echo "$knob" | sed 's/^DARKBLOOM_//' | tr 'A-Z' 'a-z')"

  # dS: step wall, hook off. ON is the shipped default, so OFF is the slower arm.
  i=0
  for cond in $WALL_ORDER; do
    i=$((i + 1))
    if [ "$cond" = A ]; then
      run_point "$(printf '%s_wall_s%02d_on' "$short" "$i")" "$knob" 1 0 0 "$WALL_STEPS"
    else
      run_point "$(printf '%s_wall_s%02d_off' "$short" "$i")" "$knob" 0 0 0 "$WALL_STEPS"
    fi
  done

  # dI: isolated per-kernel census at SPLIT=1.
  i=0
  for cond in $CENSUS_ORDER; do
    i=$((i + 1))
    if [ "$cond" = A ]; then
      run_point "$(printf '%s_cens_s%02d_on' "$short" "$i")" "$knob" 1 1 1 "$CENSUS_STEPS"
    else
      run_point "$(printf '%s_cens_s%02d_off' "$short" "$i")" "$knob" 0 1 1 "$CENSUS_STEPS"
    fi
  done
done

echo "=== done -> $OUT ==="
