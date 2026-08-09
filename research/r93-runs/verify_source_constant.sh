#!/bin/bash
# Prove that the ladder rung really is carried by the source constant.
#
# The knee sweep drove K through the environment, which the ranked host never
# sees. Before spending an official run we build the rung into the source, run
# the probe with no injection environment at all, and check that decode moves.
# K=2400 is used for the proof because its effect is unmistakable on this host;
# the tree is then left on the rung we actually intend to submit.
set -u
OUT="/tmp/r93/srcconst"
mkdir -p "$OUT"

env | grep -c DARKBLOOM || true

echo "### proof build K=2400"
bash research/r93-runs/set_ladder.sh 2400 8 2>&1 | tail -6
python3 research/decode_probe.py --steps 120 --stderr "${OUT}/w2400.err" \
  > "${OUT}/p2400.log" 2>&1
grep -E "teacher-forced|^decode steps=" "${OUT}/p2400.log"

echo "### control build K=0"
bash research/r93-runs/set_ladder.sh 0 160 2>&1 | tail -6
python3 research/decode_probe.py --steps 120 --stderr "${OUT}/w0.err" \
  > "${OUT}/p0.log" 2>&1
grep -E "teacher-forced|^decode steps=" "${OUT}/p0.log"

echo "### target rung K=240"
bash research/r93-runs/set_ladder.sh 240 8 2>&1 | tail -6
python3 research/decode_probe.py --steps 120 --stderr "${OUT}/w240.err" \
  > "${OUT}/p240.log" 2>&1
grep -E "teacher-forced|^decode steps=" "${OUT}/p240.log"

echo "done $(date -u +%H:%M:%SZ)"
