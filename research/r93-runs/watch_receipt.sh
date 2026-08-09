#!/bin/bash
# Poll one official submission until it reaches a terminal state, then dump the
# receipt. The official channel is serial and turnaround is ~20-30 minutes, so
# this is run as a supervised job rather than in the interactive terminal.
#
#   watch_receipt.sh <submission_id> <marker>
set -u

SUB="${1:?submission id required}"
MARKER="${2:?marker required}"
OUT="research/r93-runs/receipts/${MARKER}.json"
mkdir -p research/r93-runs/receipts

for i in $(seq 1 90); do
  python3 research/r91b-runs/fetch_receipt.py "$SUB" "$OUT" > /tmp/r93/watch-"${MARKER}".log 2>&1
  STATUS="$(python3 -c "
import json,sys
try:
    d=json.load(open('$OUT'))['submission']
    print(d.get('status','?'))
except Exception as e:
    print('fetch-error')
")"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) poll=$i status=$STATUS"
  case "$STATUS" in
    validating|queued|running|pending|benchmarking|fetch-error) sleep 60 ;;
    *) break ;;
  esac
done

python3 - "$OUT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["submission"]
m = d.get("officialMetrics") or {}
print("status=%s score=%s commit=%s" % (d.get("status"), d.get("officialScore"), d.get("submissionCommitSha")))
print("rejectionReason=%r error=%r" % (d.get("rejectionReason"), d.get("error")))
for k in sorted(m):
    print("  %s = %s" % (k, m[k]))
PY
