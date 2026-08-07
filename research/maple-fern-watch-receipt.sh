#!/bin/bash
# Watch one submission to a terminal status, then analyse it.
#
#   research/maple-fern-watch-receipt.sh <submission_id>
#
# Uses the cheap single-row endpoint (~13.6 KB, ~0.6 s) rather than the 17.3 MB
# feed, so a 60 s cadence costs ~0.8 MB/hour.  Observed validation durations
# over the preceding 24 h: min 0.4 min, median 20.0, p90 88.1, max 180.8, so
# the budget sits just under the supervised-launch ceiling.
#
# exit 0  = terminal status reached, analysis printed
# exit 75 = budget exhausted while still validating (the row is unaffected)

set -u

ID="${1:?usage: maple-fern-watch-receipt.sh <submission_id>}"
TGT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFLIGHT="${INFLIGHT:-/tmp/pr137_submit/inflight3.py}"
ANALYZE="$TGT/research/maple-fern-pr137-analyze-receipt.py"
POLL=60
BUDGET=10500

start=$(date +%s)
echo "=== watch_receipt start $(date -u +%FT%TZ) ==="
echo "id: $ID   poll: ${POLL}s   budget: $((BUDGET / 60)) min"

n=0
while :; do
    now=$(date +%s)
    el=$((now - start))
    if [ "$el" -ge "$BUDGET" ]; then
        echo "=== budget exhausted at $(date -u +%FT%TZ), still non-terminal ==="
        exit 75
    fi
    n=$((n + 1))
    out=$(python3 "$INFLIGHT" "$ID" 2>&1)
    rc=$?
    if [ "$rc" -ne 0 ] || [ $((n % 10)) -eq 1 ]; then
        echo "--- poll $n at $(date -u +%FT%TZ) (elapsed $((el / 60)) min) rc=$rc ---"
        echo "$out"
    fi
    if [ "$rc" -eq 1 ]; then
        echo "=== terminal at $(date -u +%FT%TZ) after $((el / 60)) min ==="
        python3 "$ANALYZE" "$ID"
        exit 0
    fi
    sleep "$POLL"
done
