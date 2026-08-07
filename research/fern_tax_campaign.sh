#!/usr/bin/env bash
# Research-only: dispatch-tax attribution battery (PR #268, maple-fern).
#
# Requires the instrumented worker:
#   git apply research/fern_tax_device_counters.patch
#   git apply research/fern_tax_inject.patch
#   CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
#     swift build -c release --force-resolved-versions \
#       --scratch-path .build-worker --product mlxfast-runtime-worker
#
# Every arm is one worker process driving the same golden teacher-forced
# decode, with a palindromic K schedule repeated `--blocks` times so linear
# drift cancels inside each block.  Arms differ only in what extra work the
# instrument injects and where.
set -u
cd "$(dirname "$0")/.."
OUT=${OUT:-/tmp/fern268}
BLOCKS=${BLOCKS:-6}
STEPS=${STEPS:-216}
DROP=${DROP:-16}
mkdir -p "$OUT"

# In-chain schedule: K copies at each of 40 live decode sites per step.
SITE_SCHED=0,1,2,4,4,2,1,0
# Off-chain schedule: the SAME dispatch counts (40*K) issued off the
# critical path, so the two families are directly comparable.
BATCH_SCHED=0,40,80,160,160,80,40,0

run() { # name mode schedule bytes [spin_ns]
  local name=$1 mode=$2 sched=$3 bytes=$4 spin=${5:-1400}
  if [ -s "$OUT/$name.tsv" ]; then
    echo "== skip $name (already present) =="
    return 0
  fi
  echo "== arm $name: mode=$mode sched=$sched bytes=$bytes spin_ns=$spin =="
  python3 research/fern_tax_probe.py \
    --mode "$mode" --schedule "$sched" --blocks "$BLOCKS" \
    --steps-per-segment "$STEPS" --drop "$DROP" --bytes "$bytes" \
    --spin-ns "$spin" \
    --out "$OUT/$name.tsv" --stderr "$OUT/$name.err" \
    > "$OUT/$name.log" 2>&1
  local rc=$?
  tail -n 24 "$OUT/$name.log"
  echo "-- arm $name exit=$rc --"
  [ $rc -le 1 ] || mv -f "$OUT/$name.tsv" "$OUT/$name.tsv.bad" 2>/dev/null
  return 0
}

# ---- Part A / Part B -------------------------------------------------------
# A0+B1: in-chain self-fusion refund. K chained identity multiplies in front
#        of the T0b_qkv consumer -- the PR #241 wiring, now with counters.
run chain40   chain40  "$SITE_SCHED"  8192
# A2/E1: same 40 encode positions, GPU work replaced by pure CPU busy-spin.
run spin40    spin40   "$SITE_SCHED"  8192 1400
# A1: identical dispatch counts, dependent chain, OFF the critical path.
run chain     chain    "$BATCH_SCHED" 8192
# A1: identical dispatch counts, independent (no barriers), off-path.
run indep     indep    "$BATCH_SCHED" 8192
# A5/E4: identical dispatch counts, one distinct input resource per dispatch.
run distinct  distinct "$BATCH_SCHED" 8192
# B2: diamond control -- two parallel producers into one consumer, minus one.
run diamond1  diamond1 "$BATCH_SCHED" 8192
run diamond2  diamond2 "$BATCH_SCHED" 8192
# A4/E3: in-chain dirty-footprint sweep at matched dispatch count.
run fat40_256 fat40    "$SITE_SCHED"  256
run fat40_8k  fat40    "$SITE_SCHED"  8192
run fat40_256k fat40   "$SITE_SCHED"  262144
run fat40_4m  fat40    "$SITE_SCHED"  4194304
# A5/E4 in-chain: same as fat40_8k but K distinct input resources.
run dist40_8k dist40   "$SITE_SCHED"  8192

echo "== campaign done -> $OUT =="
ls -la "$OUT"
