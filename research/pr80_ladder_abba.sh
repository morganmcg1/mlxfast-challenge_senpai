#!/bin/bash
# PR #80 position-balanced M4 screen of the attention scale-plane ladder.
#
# All three arms are the SAME binary; only DARKBLOOM_* selection differs, so no
# rebuild sits between arms and no code-layout confound can be introduced.
#
#   B = lane-major QKV + lane-major o_proj, no pairwise halving
#   C = B + pairwise-halved QKV scale bank
#   D = C + pairwise-halved o_proj scale bank   (shipping default)
#
# Predicted per-step scale-plane read reduction from the measured escape-adjusted
# byte ledger (research/pr80_byte_ledger.py), at the M4 Pro 260.2 GB/s figure:
#   B->C  12.365 MB -> 47.5 us/step
#   C->D   9.635 MB -> 37.0 us/step
#   B->D  22.000 MB -> 84.6 us/step
# decode_probe-class run-to-run spread on this host is ~15 us, so every rung
# should clear noise by 2.5x or more if the kernels behave as designed.
#
# Position balance: one discarded warm-up arm, then four blocks whose order
# alternates so each arm's positions sum to 26 and each block of three contains
# every arm exactly once. Smooth thermal drift therefore cancels.
#
#   pos:  1 2 3 | 4 5 6 | 7 8 9 | 10 11 12
#   arm:  B C D | D C B | B C D | D  C  B
set -u
cd "$(dirname "$0")/.."

STEPS="${PR80_STEPS:-1200}"
WARMUP="${PR80_WARMUP:-60}"

CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions --scratch-path .build-worker \
  --product mlxfast-runtime-worker 2>&1 | tail -2 || exit 1

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
  local envs=""
  case "${arm}" in
    B) envs="DARKBLOOM_ATTN_SCALE_PAIRWISE_QKV=0 DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0" ;;
    C) envs="DARKBLOOM_ATTN_SCALE_PAIRWISE_OPROJ=0" ;;
    D) envs="" ;;
  esac
  echo "=== ${pos} arm=${arm} t=$(date -u +%H:%M:%S) thermal=$(thermal)"
  # shellcheck disable=SC2086
  /usr/bin/env ${envs} \
    python3 research/frieren_host_cpu_probe.py \
      --warmup-steps "${WARMUP}" --measure-steps "${STEPS}" \
      --label "${pos}-${arm}" 2>/dev/null
}

run_arm p00-discard D
for spec in "p01 B" "p02 C" "p03 D" "p04 D" "p05 C" "p06 B" \
            "p07 B" "p08 C" "p09 D" "p10 D" "p11 C" "p12 B"; do
  # shellcheck disable=SC2086
  run_arm ${spec}
done
echo "=== done t=$(date -u +%H:%M:%S) thermal=$(thermal)"
