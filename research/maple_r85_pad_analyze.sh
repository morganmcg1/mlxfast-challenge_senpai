#!/usr/bin/env bash
# R85-C stage-3 analysis: address displacement plus its own positive control.
# Read-only; safe to re-run.
#
# ORDER is "halved halved_pad halved_pad halved base halved halved base", so
# adjacent duplexes at offset 0 are (halved,halved_pad) forward, then reverse,
# then (base,halved) forward, then reverse. Offset 1 exposes two same-arm
# duplexes, which give the in-session null floor for free.
#
#   padaddr   halved   -> halved_pad  16 KiB x PAD_PAGES displacement per plane
#   posctl    base     -> halved      within-session replay of PR #443's effect
#   padnull   halved_pad duplex       null floor, pad arm
#   armnull   halved     duplex       null floor, halved arm
set -uo pipefail

ARMS_DIR=${ARMS_DIR:-/tmp/maple-r85-pad-arms}
OUT_DIR=${OUT_DIR:-research/maple-r85-logs}
STEPS=${STEPS:-33}
STATS=research/maple_r85_arm_stats.py

mkdir -p "$OUT_DIR"
shopt -s nullglob
LOGS=("$ARMS_DIR"/[0-9][0-9]-rep*.err)
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

run padaddr halved halved_pad 0 --scale-to-n 24
run posctl base halved 0 --scale-to-n 24
run padnull halved_pad halved_pad 1 --scale-to-n 24
run armnull halved halved 1 --scale-to-n 24

for anchor in dense_down_residual residual_rms_router; do
  run "padaddr-anchor-$anchor" halved halved_pad 0 --control "$anchor" --only-giveback
done
