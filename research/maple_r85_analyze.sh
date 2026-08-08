#!/usr/bin/env bash
# R85-C analysis driver: turn the four-arm counterbalanced GPUPROF logs into the
# contrasts the placement hypothesis needs. Read-only; safe to re-run.
#
#   base    -> dose_one   placement/footprint only (the crux)
#   dose_one-> halved     read effect only (recovery of PR #443's win)
#   base    -> dose_two   dose response (capacity vs address lottery)
#   base    -> base       in-session null floor (offset 1)
#   dose_one-> dose_two   counterbalanced second dose step (offset 1)
set -uo pipefail

ARMS_DIR=${ARMS_DIR:-/tmp/maple-r85-arms}
OUT_DIR=${OUT_DIR:-research/maple-r85-logs}
STEPS=${STEPS:-33}
STATS=research/maple_r85_arm_stats.py

mkdir -p "$OUT_DIR"
shopt -s nullglob
LOGS=("$ARMS_DIR"/[0-9]*.err)
if ((${#LOGS[@]} == 0)); then
  echo "no arm logs under $ARMS_DIR" >&2
  exit 1
fi
echo "arm logs: ${#LOGS[@]}"

run() { # tag base cand offset [extra...]
  local tag=$1 a=$2 b=$3 off=$4
  shift 4
  echo
  echo "################ $tag  ($a -> $b, offset $off) ################"
  python3 "$STATS" --steps "$STEPS" --arms "$a" "$b" --offset "$off" \
    --json-out "$OUT_DIR/r85c-$tag.json" "$@" "${LOGS[@]}"
}

run placement base dose_one 0 --scale-to-n 24
run readonly dose_one halved 0 --scale-to-n 24
run doseresponse base dose_two 0 --scale-to-n 24
run null base base 1 --scale-to-n 24
run dosestep dose_one dose_two 1 --scale-to-n 24

for anchor in dense_down_residual residual_rms_router decode_router_top8_ordinal_table_norm; do
  run "placement-anchor-$anchor" base dose_one 0 --control "$anchor" --only-giveback
done
