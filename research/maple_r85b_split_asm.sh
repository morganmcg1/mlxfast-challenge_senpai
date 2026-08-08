#!/bin/bash
# Research-only (PR #456): binary-level body identity for the split.
#
# The symbol audit in maple-fern-r85b-binary-forensics.md shows the split
# preserves the defined-symbol multiset. That is necessary but not sufficient:
# a symbol can survive with a different body. This disassembles each matching
# symbol in both linked workers and compares instruction streams, which is the
# strongest available closure of mechanism M1 (semantic change).
#
# base-vs-cand is the effect. cand-vs-cand2 is the determinism control: it
# must come back fully identical, because those two builds share source.
set -uo pipefail

SNAP="${SNAP:-/tmp/maple-r85b-snap}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for needle in LagunaRuntime 12MLXFastModel; do
  for pair in "base cand" "cand cand2"; do
    set -- $pair
    echo
    echo "############################################################"
    echo "# asm $1 vs $2 :: needle=$needle"
    echo "############################################################"
    python3 "$HERE/fern_emit_compare.py" asm \
      "$SNAP/$1/mlxfast-runtime-worker" \
      "$SNAP/$2/mlxfast-runtime-worker" \
      "$needle"
    echo "# exit=$?"
  done
done
echo
echo "########## asm done ##########"
