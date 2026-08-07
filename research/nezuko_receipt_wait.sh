#!/usr/bin/env bash
# Wait for one mlxfast submission to reach a terminal status, then dump its
# raw row (including the full officialMetrics the CLI table truncates).
#
#   RECEIPT=<uuid> [OUT=/tmp/nez_wait] [MAX_WAIT_SEC=5400] bash research/nezuko_receipt_wait.sh
#
# Ops lesson this script exists to encode: the `mlxfast submissions` listing can
# transiently omit a row that is still validating. A dispatcher that infers
# "terminal" from an absent row, or from a busy-count of zero, reports a false
# terminal. Only an explicit terminal status on the submission's own endpoint
# counts here; every other observation, including a failed fetch, keeps waiting.
set -u

RECEIPT="${RECEIPT:?set RECEIPT=<submission uuid>}"
OUT="${OUT:-/tmp/nez_wait}"
MAX_WAIT_SEC="${MAX_WAIT_SEC:-5400}"
INTERVAL="${INTERVAL:-60}"
API="https://api.mlx.fast/api/submissions/${RECEIPT}"

TOKEN=""
for v in MLXFAST_API_TOKEN YUKON_API_TOKEN SUPABASE_ACCESS_TOKEN; do
  eval "cand=\${${v}:-}"
  if [ -n "${cand}" ]; then TOKEN="${cand}"; echo "TOKEN_SOURCE=${v}"; break; fi
done
if [ -z "${TOKEN}" ]; then echo "NO_TOKEN_FOUND"; exit 2; fi

mkdir -p "${OUT}"
JSON="${OUT}/receipt.json"
BUSY_RE='^(validating|queued|running|pending|building)$'

echo "WAIT_START $(date -u +%Y-%m-%dT%H:%M:%SZ) receipt=${RECEIPT}"
deadline=$(( $(date +%s) + MAX_WAIT_SEC ))
status="unknown"
while [ "$(date +%s)" -lt "${deadline}" ]; do
  if curl -sS -f -H "Authorization: Bearer ${TOKEN}" "${API}" > "${JSON}.tmp" 2>"${OUT}/curl.err"; then
    mv "${JSON}.tmp" "${JSON}"
    status="$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
d=d.get('submission',d)
print(d.get('status') or 'null')
" "${JSON}" 2>/dev/null || echo fetch_parse_error)"
  else
    status="fetch_error"
  fi
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) status=${status}"
  if ! echo "${status}" | grep -Eq "${BUSY_RE}" \
     && [ "${status}" != "unknown" ] \
     && [ "${status}" != "null" ] \
     && [ "${status}" != "fetch_error" ] \
     && [ "${status}" != "fetch_parse_error" ]; then
    echo "RECEIPT_TERMINAL $(date -u +%Y-%m-%dT%H:%M:%SZ) status=${status}"
    break
  fi
  sleep "${INTERVAL}"
done

echo "----- RAW ROW -----"
if [ -f "${JSON}" ]; then
  python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
d=d.get('submission',d)
d.pop('note',None)   # the note is our own 25 KiB markdown; do not echo it
print(json.dumps(d,indent=2,sort_keys=True))
" "${JSON}"
else
  echo "NO_JSON_CAPTURED"
fi
echo "WAIT_DONE $(date -u +%Y-%m-%dT%H:%M:%SZ) status=${status} json=${JSON}"
