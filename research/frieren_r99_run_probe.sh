#!/bin/bash
# Research-only driver (not part of the submission surface).
#
# Regenerates the r99-A variant set from the committed base with the two
# generators, then runs every preregistered A/B leg through
# research/nezuko_r98_ab_kernel_probe.swift. Variants are written to /tmp and
# the scored source is restored with `git checkout` after each one, so the
# worktree is untouched when this exits.
#
# Each contrast is run in both arm orders. The probe's first sweep showed a
# base-vs-base null of about -1 %, so the CAND slot is not free of position
# bias; (FWD - REV) / 2 cancels any bias common to the two orders. Within-run
# paired t values are also far more confident than the between-sweep spread,
# so the whole leg set is repeated and the sweep is the unit of replication.
#
# Usage: research/frieren_r99_run_probe.sh [sweeps]
set -u

SWEEPS=${1:-1}
P=Sources/MLXFastModel/LagunaRuntimeModel.swift
BASE_SHA=c6c66344d9848d95158edc31f31943aabe4de079
SLIDING=laguna_sliding_fused_attn_ring_v1
FULL=laguna_full_fused_attn_grow_v1
PROBE=/tmp/nezab

# The candidate is committed, so `git checkout -- "$P"` no longer yields the
# base text; every variant is regenerated from the pinned base blob instead.
git checkout "$BASE_SHA" -- "$P"
cp "$P" /tmp/v_base.swift

python3 research/nezuko_r96_gen4deep.py 4
cp "$P" /tmp/v_d4.swift
python3 research/frieren_r99_epilogue.py float4 "$SLIDING"
cp "$P" /tmp/v_d4epi.swift
git checkout "$BASE_SHA" -- "$P"

python3 research/nezuko_r96_gen4deep.py 8
cp "$P" /tmp/v_d8.swift
git checkout "$BASE_SHA" -- "$P"

python3 research/frieren_r99_epilogue.py float4 "$SLIDING"
cp "$P" /tmp/v_epi.swift
python3 research/frieren_r99_epilogue.py float4 "$FULL"
cp "$P" /tmp/v_epiboth.swift
git checkout "$BASE_SHA" -- "$P"

echo "worktree after variant generation:"
git status --porcelain
echo

run() {
  echo "@@LEG $1 $2"
  "$PROBE" "/tmp/v_$3.swift" "/tmp/v_$4.swift" "${5:-$SLIDING}"
  echo "@@END"
}

# The very first leg of a fresh process pays shader-cache and clock-ramp cost
# that lands entirely in its lowest-K rows; it is run and discarded.
run warmup FWD base base

for s in $(seq 1 "$SWEEPS"); do
  echo "@@SWEEP $s"
  run null  FWD base base
  run d4    FWD base d4
  run epi   FWD base epi
  run d4epi FWD base d4epi
  run d8    FWD base d8
  run full  FWD base epiboth "$FULL"
  run full  REV epiboth base "$FULL"
  run d8    REV d8    base
  run d4epi REV d4epi base
  run epi   REV epi   base
  run d4    REV d4    base
  run null  REV base  base
done

git checkout HEAD -- "$P"
echo "final worktree:"
git status --porcelain
