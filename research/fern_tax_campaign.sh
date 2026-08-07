#!/usr/bin/env bash
# Research-only: dispatch-tax attribution battery (PR #268, maple-fern).
#
# Requires the instrumented worker:
#   git apply research/fern_tax_device_counters.patch
#   git apply research/fern_tax_inject.patch
#   CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
#     swift build -c release --force-resolved-versions \
#       --scratch-path .build-worker --product mlxfast-runtime-worker
#   git checkout -- Sources Vendor      # instruments never land in the tree
#
# Every arm is one worker process driving the same golden teacher-forced
# decode, with a palindromic K schedule repeated `--blocks` times so linear
# drift cancels inside each block.  Arms differ only in what extra work the
# instrument injects and where.  Arms are ordered by decision value: if the
# battery is cut short, the arms that already ran are the ones that matter.
set -u
cd "$(dirname "$0")/.."
OUT=${OUT:-/tmp/fern268}
BLOCKS=${BLOCKS:-6}
STEPS=${STEPS:-216}
DROP=${DROP:-16}
mkdir -p "$OUT"

# In-chain schedule: K extra dispatches at each of 40 live decode sites.
SITE_SCHED=0,1,2,4,4,2,1,0
# Off-chain schedule: the SAME dispatch counts (40*K) issued off the
# critical path, so the two families are directly comparable.
BATCH_SCHED=0,40,80,160,160,80,40,0

run() { # name mode schedule bytes pool anchor blocks spin_ns
  local name=$1 mode=$2 sched=$3 bytes=$4 pool=$5 anchor=$6 blocks=$7 spin=$8
  if [ -s "$OUT/$name.tsv" ]; then
    echo "== skip $name (already present) =="
    return 0
  fi
  echo "== arm $name: mode=$mode sched=$sched bytes=$bytes pool=$pool" \
       "anchor=$anchor blocks=$blocks spin_ns=$spin =="
  python3 research/fern_tax_probe.py \
    --mode "$mode" --schedule "$sched" --blocks "$blocks" \
    --steps-per-segment "$STEPS" --drop "$DROP" --bytes "$bytes" \
    --pool "$pool" --anchor "$anchor" --spin-ns "$spin" \
    --out "$OUT/$name.tsv" --stderr "$OUT/$name.err" \
    > "$OUT/$name.log" 2>&1
  local rc=$?
  tail -n 24 "$OUT/$name.log"
  echo "-- arm $name exit=$rc --"
  [ $rc -le 1 ] || mv -f "$OUT/$name.tsv" "$OUT/$name.tsv.bad" 2>/dev/null
  return 0
}

# --- tier 1: the arms that decide the question -----------------------------
# B1 headline: K chained identity multiplies strictly inside the live chain,
# in front of the T0b_qkv consumer -- the PR #241 wiring, now with counters.
run chain40    chain40  "$SITE_SCHED"  8192      1   1 "$BLOCKS" 1400
# A2/E1: same 40 encode positions, GPU work replaced by pure CPU busy-spin.
run spin40     spin40   "$SITE_SCHED"  8192      1   1 "$BLOCKS" 1400
# A5/E4 in-chain: K serial dispatches, each reading a DISTINCT source.
run dist40_8k  dist40   "$SITE_SCHED"  8192    256   1 "$BLOCKS" 1400
# A4/E3 matched control: identical K, identical bytes, ONE reused source.
run fat40_8k   fat40    "$SITE_SCHED"  8192      1   1 "$BLOCKS" 1400
# A1/E2: identical dispatch counts, dependent chain, OFF the critical path.
run chain      chain    "$BATCH_SCHED" 8192      1   1 "$BLOCKS" 1400
# A1/E2: identical dispatch counts, independent (no barriers), off-path.
run indep      indep    "$BATCH_SCHED" 8192      1   1 "$BLOCKS" 1400

# --- tier 2: separate footprint from resource count ------------------------
# A4/E3 in-chain dirty-footprint sweep at matched dispatch count and pool=1.
run fat40_256  fat40    "$SITE_SCHED"  256       1   1 "$BLOCKS" 1400
run fat40_64k  fat40    "$SITE_SCHED"  65536     1   1 "$BLOCKS" 1400
run fat40_256k fat40    "$SITE_SCHED"  262144    1   1 "$BLOCKS" 1400
# A5/E4 at 32x smaller footprint: if the dist40-vs-fat40 gap survives here it
# is resource bookkeeping, not cache traffic.
run dist40_256 dist40   "$SITE_SCHED"  256     256   1 "$BLOCKS" 1400

# --- tier 3: anchor controls and the diamond -------------------------------
# Same site, same dispatches, but depending on nothing live: prices how much
# of the in-chain cost is serialization rather than launch.
run fat40_8k_free  fat40  "$SITE_SCHED" 8192    1   0 "$BLOCKS" 1400
run dist40_8k_free dist40 "$SITE_SCHED" 8192  256   0 "$BLOCKS" 1400
# A5/E4 off-path distinct sources.
run distinct   distinct "$BATCH_SCHED" 8192    256   1 "$BLOCKS" 1400
# B2 diamond control: same join count, one extra parallel producer per join.
run diamond1   diamond1 "$BATCH_SCHED" 8192      1   1 "$BLOCKS" 1400
run diamond2   diamond2 "$BATCH_SCHED" 8192      1   1 "$BLOCKS" 1400
# A4 tail of the footprint sweep. Bandwidth-dominated and slow per step, so
# it runs last and with fewer blocks.
run fat40_4m   fat40    "$SITE_SCHED"  4194304   1   1 2        1400

echo "== campaign done -> $OUT =="
ls -la "$OUT"
