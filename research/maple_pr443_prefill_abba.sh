#!/bin/bash
# Research-only (PR #443): paired 512-token prefill timing for the halved
# shared gate/up scale plane (`DARKBLOOM_SHARED_SCALE_HALVED`).
#
# Both shared-QMV dispatch sites guard on `x.dims(1, 1, hiddenSize)`, so the
# halved plane is unreachable from a 512-token prefill and the expected effect
# is exactly zero. This arm exists to *show* that, not to find a win: it is the
# hard-floor axis (rule 17), and the plane is still built and resident, so an
# allocator or residency side effect on prefill has to be excluded by
# measurement rather than by argument.
#
# Runs on the clean (unhooked) worker; `--steps 8` keeps each process short
# while still confirming the arm actually took the halved path.
#
#   OUT=/tmp/maple-pr443-prefill REPS=4 bash research/maple_pr443_prefill_abba.sh
set -u
REPS=${REPS:-4}
STEPS=${STEPS:-8}
OUT=${OUT:-/tmp/maple-pr443-prefill}
ORDER=${ORDER:-"off halved halved off"}
mkdir -p "$OUT"

idx=0
for rep in $(seq 1 "$REPS"); do
  for arm in $ORDER; do
    idx=$((idx + 1))
    tag=$(printf "%02d-rep%s-%s" "$idx" "$rep" "$arm")
    unset DARKBLOOM_SHARED_SCALE_HALVED
    case "$arm" in
      halved) export DARKBLOOM_SHARED_SCALE_HALVED=1 ;;
    esac
    echo "=== $tag ==="
    python3 research/decode_probe.py --steps "$STEPS" --prefill \
      --stderr "$OUT/$tag.err" >"$OUT/$tag.log" 2>&1
    status=$?
    grep -E "prefill 512 tokens|per steady step" "$OUT/$tag.log"
    grep -c "shared gate/up halved scale plane" "$OUT/$tag.err" \
      | sed 's/^/halved-plane certificate lines: /'
    echo "exit=$status"
    [ "$status" -eq 0 ] || exit "$status"
  done
done
echo "logs in $OUT"
