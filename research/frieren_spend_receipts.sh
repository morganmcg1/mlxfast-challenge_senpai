#!/usr/bin/env bash
# Research-only: dispatch the authorized official receipts for one configuration.
#
# The platform serializes ranked runs at one in-flight submission per account
# ({"code":"conflict"}), so each receipt has to wait for the slot rather than
# fail. Success is detected by the submission-row count rising, which does not
# depend on the CLI's success text.
#
# Usage: research/frieren_spend_receipts.sh [receipt_count]
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH="${HOME}/.local/bin:${PATH}"

NOTE="research/frieren-pr23-r2-submission-note.md"
MODEL="anthropic/claude-opus-5"
WANT="${1:-3}"
MAX_ATTEMPTS=150

count_rows() {
    mlxfast submissions 2>/dev/null | grep -cE '^[0-9a-f]{7} '
}

base="$(count_rows)"
echo "=== starting with ${base} submission rows, want ${WANT} new receipts ==="

sent=0
attempt=0
while [ "${sent}" -lt "${WANT}" ] && [ "${attempt}" -lt "${MAX_ATTEMPTS}" ]; do
    attempt=$((attempt + 1))
    out="$(mlxfast submit --note-file "${NOTE}" --model "${MODEL}" 2>&1 | tail -3)"
    now="$(date -u +%H:%M:%S)"
    rows="$(count_rows)"
    if [ "${rows}" -gt "${base}" ]; then
        sent=$((sent + 1))
        base="${rows}"
        echo "=== ${now} RECEIPT ${sent}/${WANT} DISPATCHED (attempt ${attempt}) ==="
        echo "${out}"
        mlxfast submissions 2>&1 | tail -2
    elif printf '%s' "${out}" | grep -q '"code":"conflict"'; then
        [ $((attempt % 10)) -eq 1 ] && echo "[${now}] attempt ${attempt}: slot busy, waiting"
    else
        echo "=== ${now} UNEXPECTED submit response on attempt ${attempt}; stopping ==="
        echo "${out}"
        break
    fi
    sleep 60
done

echo "=== dispatched ${sent} of ${WANT} receipts in ${attempt} attempts ==="
mlxfast submissions 2>&1 | tail -6
