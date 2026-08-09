#!/bin/bash
# Research-only driver (not part of the submission surface).
#
# Regenerates the r99-A variant set from the committed base with the two
# generators, then runs every preregistered A/B leg through
# research/nezuko_r98_ab_kernel_probe.swift. Variants are written to /tmp and
# the scored source is restored with `git checkout` after each one, so the
# worktree is untouched when this exits.
#
# Usage: research/frieren_r99_run_probe.sh
set -u

P=Sources/MLXFastModel/LagunaRuntimeModel.swift
SLIDING=laguna_sliding_fused_attn_ring_v1
FULL=laguna_full_fused_attn_grow_v1
PROBE=/tmp/nezab

git checkout -- "$P"
cp "$P" /tmp/v_base.swift

python3 research/nezuko_r96_gen4deep.py 4
cp "$P" /tmp/v_d4.swift
python3 research/frieren_r99_epilogue.py float4 "$SLIDING"
cp "$P" /tmp/v_d4epi.swift
git checkout -- "$P"

python3 research/nezuko_r96_gen4deep.py 8
cp "$P" /tmp/v_d8.swift
git checkout -- "$P"

python3 research/frieren_r99_epilogue.py float4 "$SLIDING"
cp "$P" /tmp/v_epi.swift
python3 research/frieren_r99_epilogue.py float4 "$FULL"
cp "$P" /tmp/v_epiboth.swift
git checkout -- "$P"

echo "worktree after variant generation:"
git status --porcelain
echo

run() {
  echo "================ LEG $1 : base=$2 cand=$3 kernel=${4:-$SLIDING}"
  "$PROBE" "/tmp/v_$2.swift" "/tmp/v_$3.swift" "${4:-$SLIDING}"
  echo "================ END LEG $1 (exit $?)"
  echo
}

run 0-null    base base
run 1-d4      base d4
run 1b-epi    base epi
run 1c-d4epi  base d4epi
run 1d-sign   d4   base
run 1e-d8     base d8
run 1f-full   base epiboth "$FULL"

echo "final worktree:"
git status --porcelain
