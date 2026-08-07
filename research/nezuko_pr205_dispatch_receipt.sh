#!/bin/bash
# Dispatch exactly one official mlxfast receipt for PR #205, then wait for its
# verdict.
#
# The account-wide in-flight limit is 1 submission per benchmark, so a direct
# `mlxfast submit` fails with {"code":"conflict"} whenever a sibling run is
# still validating. This retries on that specific conflict only; any other
# error stops immediately so a human reads it before a second attempt.
#
# Idempotency: `submit` is invoked at most once. After it succeeds the script
# only polls, so a re-run of the loop can never create a duplicate receipt.
set -u

export PATH="${HOME}/.local/bin:${PATH}"
cd "$(dirname "$0")/.." || exit 1

NOTE="research/nezuko-pr205-submission-note.md"
OUT=/tmp/nez_submit
mkdir -p "${OUT}"

MAX_WAIT_SEC="${MAX_WAIT_SEC:-5400}"
INTERVAL=60
BUSY_RE='validating|queued|running|pending|building'
deadline=$(( $(date +%s) + MAX_WAIT_SEC ))

ids() { mlxfast submissions 2>/dev/null | awk '{print $1}' | grep -Ex '[0-9a-f]{7}'; }
busy_count() { mlxfast submissions 2>/dev/null | grep -Ec "${BUSY_RE}"; }

ids > "${OUT}/pre_ids.txt"
echo "PRE_ID_COUNT=$(wc -l < "${OUT}/pre_ids.txt" | tr -d ' ')"

SUBMITTED=0
MY_ID=""

while [ "$(date +%s)" -lt "${deadline}" ]; do
  n=$(busy_count)
  echo "$(date -u +%FT%TZ) busy=${n} submitted=${SUBMITTED} my_id=${MY_ID:-none}"

  if [ "${SUBMITTED}" -eq 0 ]; then
    if [ "${n}" -eq 0 ]; then
      echo "SUBMIT_ATTEMPT $(date -u +%FT%TZ)"
      mlxfast submit --model "senpai" --note-file "${NOTE}" > "${OUT}/submit.txt" 2>&1
      echo "SUBMIT_RC=$?"
      cat "${OUT}/submit.txt"
      if grep -q '"error"' "${OUT}/submit.txt"; then
        if grep -qi 'in flight' "${OUT}/submit.txt"; then
          echo "SUBMIT_DEFERRED_CONFLICT"
        else
          echo "SUBMIT_HARD_ERROR"
          break
        fi
      else
        SUBMITTED=1
        echo "SUBMIT_OK $(date -u +%FT%TZ)"
      fi
    fi
  else
    if [ -z "${MY_ID}" ]; then
      ids > "${OUT}/post_ids.txt"
      MY_ID=$(comm -13 <(sort "${OUT}/pre_ids.txt") <(sort "${OUT}/post_ids.txt") | head -1)
      [ -n "${MY_ID}" ] && echo "MY_RECEIPT_ID=${MY_ID}"
    fi
    if [ -n "${MY_ID}" ]; then
      row=$(mlxfast submissions 2>/dev/null | grep -E "^${MY_ID}")
      echo "MY_ROW: ${row}"
      if ! echo "${row}" | grep -Eq "${BUSY_RE}"; then
        echo "RECEIPT_TERMINAL $(date -u +%FT%TZ)"
        break
      fi
    fi
  fi

  sleep "${INTERVAL}"
done

echo "FINAL_SUBMISSIONS"
mlxfast submissions 2>&1 | tail -6
echo "DISPATCH_DONE submitted=${SUBMITTED} my_id=${MY_ID:-none}"
