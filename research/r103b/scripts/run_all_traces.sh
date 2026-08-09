#!/bin/bash
# R103-B rungs 1+2: sequential traced decode runs (one model process at a time).
set -uo pipefail
S=/tmp/r103b/run_trace.sh
chmod +x "$S"
export STEP="${STEP:-5}"

ARMS="${ARMS:-old new new_pf0}"

for a in $ARMS; do
  case "$a" in
    old)     "$S" r103b-old old ;;
    new)     "$S" r103b-new new ;;
    new_pf0) "$S" r103b-new new_pf0 DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0 ;;
    *) echo "unknown arm $a" >&2 ;;
  esac
done
echo ALLDONE
