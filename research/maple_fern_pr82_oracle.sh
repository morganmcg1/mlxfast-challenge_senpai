#!/bin/bash
# Research-only §4.1 bit-exactness oracle for PR #82 (routed QMV router dedup).
# Not part of the submission.
#
# Reproduce with:
#   git apply research/maple-fern-pr82-oracle.patch
#   swift build -c release --force-resolved-versions --scratch-path .build-worker \
#     --product mlxfast-runtime-worker
#   git checkout -- Package.resolved Sources/   # instrument lives only in the binary
#   bash research/maple_fern_pr82_oracle.sh
#
# The instrument dispatches, per MoE layer per decode step, the *unmodified*
# in-kernel selection logic (`laguna_router_top8_extract_round` over
# `router_keys`, identical lane mapping to the promoted keys kernel) for all
# eight ranks, and compares it against the selector-published `indices[0..7]`
# that the candidate kernel now reads. Arm 1 must report 0 differences over
# every pair. Arm 2 (`DARKBLOOM_FERN_ORACLE_FAULT=1`) injects a +1 fault on
# rank 3 only and must report a difference on every emitted line; a silent
# arm 2 means the oracle is not wired to anything and arm 1 proves nothing.
set -u
cd "$(dirname "$0")/.."
STEPS="${1:-16}"
WORKER=.build-worker/release/mlxfast-runtime-worker
if [ ! -x "$WORKER" ]; then
  echo "missing $WORKER; build from research/maple-fern-pr82-oracle.patch first" >&2
  exit 1
fi

run_arm() {
  local name="$1" err="$2"
  shift 2
  echo "=== arm ${name} (steps=${STEPS}) ==="
  env "$@" DARKBLOOM_FERN_ORACLE=1 DARKBLOOM_STARTUP_MEMORY_PROFILE=full \
    python3 research/decode_probe.py --steps "$STEPS" --stderr "$err" >/dev/null
  local lines diffs
  lines=$(grep -c '^FERNORACLE ' "$err" || true)
  diffs=$(grep '^FERNORACLE ' "$err" | grep -c 'diffs=0 ' || true)
  echo "arm=${name} emitted_lines=${lines} lines_with_diffs=0: ${diffs}"
  echo "arm=${name} pairs_compared=$(( lines * 8 ))"
  echo "arm=${name} total_differing_pairs=$(
    grep -o 'diffs=[0-9]*' "$err" | cut -d= -f2 | paste -sd+ - | bc)"
  grep '^FERNORACLE ' "$err" | head -3
  echo
}

run_arm base /tmp/fern_pr82_oracle_base.err DARKBLOOM_FERN_ORACLE_FAULT=0
run_arm control /tmp/fern_pr82_oracle_fault.err DARKBLOOM_FERN_ORACLE_FAULT=1
