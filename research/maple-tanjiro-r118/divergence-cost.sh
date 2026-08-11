#!/usr/bin/env bash
# R118-A addendum: price the routing confound directly.
#
# A dose arm perturbs the shared expert numerically, so the MoE router picks a
# different top-8 on some steps (d1: 118/160 steps, d2: 60/160, deterministic and
# identical across all ten runs of each arm).  Dispatch shapes do not change --
# top-8 is top-8 -- but the gathered expert *addresses* do.  If that costs time,
# the dose arm's measured saving UNDERSTATES the interior's value and my upper
# bound is biased in my own favour's opposite direction.
#
# The test: run ship and d1 with per-step times AND per-step tokens.  ship has 0
# divergences, so ship's token stream is the golden stream.  Label each step of
# the d1 run divergent/not by comparing token streams, then compare the PAIRED
# per-step difference (ship - d1) on divergent vs non-divergent steps.  Pairing by
# step index removes the fact that divergent steps are not randomly located.
#
# Palindromic order ship,d1,d1,ship so session drift cancels.
set -u
cd "$(dirname "$0")/../.."
D=research/maple-tanjiro-r118/evidence/diverg
S="${1:-160}"
mkdir -p "${D}"
WORKER=".build-worker/release/mlxfast-runtime-worker"
[ -x "${WORKER}" ] || { echo "no worker binary at ${WORKER}"; exit 3; }

i=0
for arm in ship d1 d1 ship; do
  i=$((i+1))
  echo "=== diverg run ${i} arm ${arm} t=$(date -u +%H:%M:%S)"
  DARKBLOOM_SHARED_QMV_ARM="${arm}" python3 research/decode_probe.py \
      --steps "${S}" \
      --dump-steps "${D}/run${i}_${arm}.steps" \
      --dump-tokens "${D}/run${i}_${arm}.tokens" \
      --stderr "${D}/run${i}_${arm}.err" > "${D}/run${i}_${arm}.log" 2>&1
  echo "    rc=$? $(grep -o '[0-9]* divergences' "${D}/run${i}_${arm}.log" | head -1)"
done
echo "=== diverg done t=$(date -u +%H:%M:%S)"
