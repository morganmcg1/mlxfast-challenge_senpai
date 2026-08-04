#!/usr/bin/env bash
# Research-only: dispatch the authorized official receipts for one configuration.
#
# Two platform limits shape this. Ranked runs are serialized at one in-flight
# submission per account ({"code":"conflict"}), and the submit endpoint itself is
# rate limited - retrying once a minute trips "Rate limit reached. Try again in
# N seconds" and locks submission out for most of an hour. So poll the cheap
# listing to decide when the slot is free, call submit sparingly, and honour any
# retry-after the server hands back.
#
# Usage: research/frieren_spend_receipts.sh [receipt_count] [initial_wait_seconds]
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH="${HOME}/.local/bin:${PATH}"

NOTE="research/frieren-pr23-r2-submission-note.md"
MODEL="anthropic/claude-opus-5"
WANT="${1:-3}"
INITIAL_WAIT="${2:-0}"
MAX_POLLS=48
POLL_SECONDS=300

listing() { mlxfast submissions 2>/dev/null; }
count_rows() { listing | grep -cE '^[0-9a-f]{7} '; }
slot_busy() { listing | grep -qE '^[0-9a-f]{7} .*validating'; }

if [ "${INITIAL_WAIT}" -gt 0 ]; then
    echo "=== $(date -u +%H:%M:%S) waiting ${INITIAL_WAIT}s for the submit rate-limit window ==="
    sleep "${INITIAL_WAIT}"
fi

sent=0
polls=0
while [ "${sent}" -lt "${WANT}" ] && [ "${polls}" -lt "${MAX_POLLS}" ]; do
    polls=$((polls + 1))
    now="$(date -u +%H:%M:%S)"
    if slot_busy; then
        [ $((polls % 4)) -eq 1 ] && echo "[${now}] poll ${polls}: a submission is validating, waiting"
        sleep "${POLL_SECONDS}"
        continue
    fi
    before="$(count_rows)"
    out="$(mlxfast submit --note-file "${NOTE}" --model "${MODEL}" 2>&1 | tail -3)"
    now="$(date -u +%H:%M:%S)"
    if printf '%s' "${out}" | grep -q '"code":"conflict"'; then
        echo "[${now}] poll ${polls}: slot taken between listing and submit"
        sleep "${POLL_SECONDS}"
        continue
    fi
    retry="$(printf '%s' "${out}" | sed -n 's/.*Try again in \([0-9][0-9]*\) seconds.*/\1/p' | tail -1)"
    if [ -n "${retry}" ]; then
        echo "[${now}] poll ${polls}: rate limited, sleeping $((retry + 30))s"
        sleep $((retry + 30))
        continue
    fi
    if printf '%s' "${out}" | grep -q '"error"'; then
        echo "=== ${now} UNEXPECTED submit error, stopping ==="
        echo "${out}"
        break
    fi
    sent=$((sent + 1))
    echo "=== ${now} RECEIPT ${sent}/${WANT} DISPATCHED (rows ${before} -> $(count_rows)) ==="
    echo "${out}"
    listing | tail -1
    sleep "${POLL_SECONDS}"
done

echo "=== dispatched ${sent} of ${WANT} receipts after ${polls} polls ==="
listing | tail -6
