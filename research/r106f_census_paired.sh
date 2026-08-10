#!/usr/bin/env bash
# Stage 1 (R106-F'): paired per-family prefill census of the pinned
# ranked-baseline tree (15852ee5) and the candidate tree in one host session.
#
# SPLIT=1 gives per-dispatch family attribution (the per-family ms columns);
# SPLIT=0 gives the shipped command-buffer batching, i.e. the honest
# wall/busy/gap totals used to close each tree's ledger against its own wall.
# Slot order is counterbalanced so a linear session drift cancels in the ratio.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
BASE_WORKER="${BASE_WORKER:-/tmp/r106f/base/mlxfast-runtime-worker}"
CAND_WORKER="${CAND_WORKER:-$REPO/.build-worker/release/mlxfast-runtime-worker}"
OUT="${OUT:-research/pr270-logs-r106f}"
REPS="${REPS:-6}"
TOP="${TOP:-90}"
SETTLE="${SETTLE:-20}"
# slot spec: <arm>:<split>
ORDER="${ORDER:-cand:1 base:1 base:0 cand:0}"
mkdir -p "$OUT"
export DARKBLOOM_STARTUP_MEMORY_PROFILE=full
export DARKBLOOM_GPU_PROFILE=1

for w in "$BASE_WORKER" "$CAND_WORKER"; do
  [ -x "$w" ] || { echo "FATAL: worker missing: $w" >&2; exit 1; }
  echo "$(shasum -a 256 "$w" | cut -d' ' -f1)  $(stat -f '%z' "$w") bytes  $w"
done

i=0
for slot in $ORDER; do
  i=$((i + 1))
  arm="${slot%%:*}"
  split="${slot##*:}"
  case "$arm" in
    cand) W="$CAND_WORKER" ;;
    base) W="$BASE_WORKER" ;;
    *) echo "FATAL: unknown arm $arm" >&2; exit 1 ;;
  esac
  echo "### settle ${SETTLE}s"
  sleep "$SETTLE"
  echo "### slot $i arm=$arm split=$split worker=$W"
  tag="$OUT/census.$arm.split$split"
  PREFILL_PROBE_WORKER="$W" DARKBLOOM_GPU_PROFILE_SPLIT="$split" \
    python3 research/prefill_probe.py \
      --reps "$REPS" --profile --profile-top "$TOP" \
      --weights "$REPO/weights" \
      --stderr "$tag.worker.err" \
      2>&1 | tee "$tag.log"
  echo "exit=${PIPESTATUS[0]}"
done
echo "### done"
