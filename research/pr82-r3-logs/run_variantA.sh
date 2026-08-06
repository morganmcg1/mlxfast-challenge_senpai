#!/bin/bash
# r3 item 2: interleaved BASE/CAND replication of PR #82 Variant A.
# One build, env-gated arms, ABABAB so session drift cancels between cells.
set -u
cd "$(dirname "$0")/../.."
out=research/pr82-r3-logs

for tag in base_a cand_a base_b cand_b base_c cand_c; do
  case "$tag" in
    cand_*) export DARKBLOOM_ROUTED_QMV_INDICES=1 ;;
    *)      unset DARKBLOOM_ROUTED_QMV_INDICES ;;
  esac
  echo "=== arm $tag (DARKBLOOM_ROUTED_QMV_INDICES=${DARKBLOOM_ROUTED_QMV_INDICES:-unset}) ==="
  DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 \
    python3 research/decode_probe.py --steps 200 --profile --profile-top 44 \
    --stderr "/tmp/pr82r3_${tag}.err" > "${out}/${tag}.txt" 2>&1
  echo "arm $tag rc=$? $(grep -h 'per steady step' "${out}/${tag}.txt")"
done
echo "all variantA arms done"
