#!/bin/bash
# PR #80 follow-on rung: does the lane-major o_proj READ path actually pay?
#
# The main ladder (pr80_ladder_abba.sh) covers B->C->D. It cannot cover the
# promoted frontier's block-narrow o_proj plane (arm A), because arm A needs a
# different binary and a mid-ladder rebuild is exactly the confound the
# single-binary design exists to avoid.
#
# This rung substitutes a bound that IS reachable on the same binary:
#
#   S = lane-major QKV, o_proj on the untouched STOCK plane   (39.32 MB/step)
#   B = lane-major QKV, o_proj lane-major                     (20.11 MB/step)
#
# Arm A's block-narrow o_proj plane sits strictly between S and B in bytes
# (252/336 B per row against stock 384/512 and lane-major 193/257) and decodes
# from three planes rather than two. So if S->B resolves as a gain at roughly
# the byte-model rate, the lane-major o_proj read path -- including its escape
# address-select, which is the one construct a Metal compiler could plausibly
# if-convert into a double load -- is healthy, and A->B being a REGRESSION is
# not credible.
#
#   S->B  19.215 MB -> 73.8 us/step at the M4 Pro 260.2 GB/s figure
#
# Position balance: discard, then B S S B B S S B (each arm's positions sum 18).
set -u
cd "$(dirname "$0")/.."

STEPS="${PR80_STEPS:-1200}"
WARMUP="${PR80_WARMUP:-60}"

MACMON="${HOME}/bin/macmon"
thermal() {
  if [ -x "${MACMON}" ]; then
    "${MACMON}" pipe -s1 2>/dev/null | jq -c \
      '{cpu_temp:.temp.cpu_temp_avg,gpu_temp:.temp.gpu_temp_avg,gpu_pw:.gpu_power}' 2>/dev/null
  else
    echo "no-macmon"
  fi
}

run_arm() {
  local pos="$1" arm="$2"
  local envs="DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV=0 DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0"
  if [ "${arm}" = "S" ]; then
    envs="${envs} DARKBLOOM_ATTN_SCALE_NARROW_OPROJ=0"
  fi
  echo "=== ${pos} arm=${arm} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  # shellcheck disable=SC2086
  /usr/bin/env ${envs} \
    python3 research/frieren_host_cpu_probe.py \
      --warmup-steps "${WARMUP}" --measure-steps "${STEPS}" \
      --label "${pos}-${arm}" 2>/dev/null
}

run_arm p00-discard B
for spec in "p01 B" "p02 S" "p03 S" "p04 B" \
            "p05 B" "p06 S" "p07 S" "p08 B"; do
  # shellcheck disable=SC2086
  run_arm ${spec}
done
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
