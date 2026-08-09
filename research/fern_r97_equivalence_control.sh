#!/bin/bash
# Upstream-equivalence oracle with both R97-A dense planes forced to the stock
# BF16 path (research only).
#
# The oracle's zero-tolerance check failed on this M4 Pro host at the prefill
# step with maximumAbsoluteLogitError = 0.125 while all eight decode steps were
# exactly 0. `agents.md` says to test the unchanged base when a non-M5 host
# disagrees. Setting both flags to "0" selects the stock BF16 gate/up and down
# planes, which is bit-identical to the base for these two dispatches, so a
# failure that survives this script is not attributable to the compaction.
cd "$(dirname "$0")/.." || exit 1
export DARKBLOOM_DENSE_BEXP_GATE_UP=0
export DARKBLOOM_DENSE_BEXP_DOWN=0
exec bash research/run_upstream_equivalence.sh
