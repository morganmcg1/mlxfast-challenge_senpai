#!/bin/bash
# Block until one mlxfast submission leaves a non-terminal state, then exit 0.
# Exists so the receipt wait is a supervised process instead of an interactive
# polling loop; it holds no model memory and takes no benchmark lock.
#
# usage: frieren_pr35_await_receipt.sh <short-submission-id> [max-seconds] [interval-seconds]

set -uo pipefail

SUB="${1:?short submission id required}"
MAX="${2:-3300}"
IVL="${3:-60}"

deadline=$(( $(date +%s) + MAX ))
attempt=0
cli_errors=0

while :; do
  attempt=$(( attempt + 1 ))
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  line="$(mlxfast submissions 2>/dev/null | grep -E "^${SUB}" | tail -1)"
  if [ -z "$line" ]; then
    cli_errors=$(( cli_errors + 1 ))
    echo "[$now] attempt=${attempt} no row for ${SUB} (cli_errors=${cli_errors})"
    if [ "$cli_errors" -ge 20 ]; then
      echo "RECEIPT_WAIT: giving up, ${cli_errors} consecutive lookup failures"
      exit 3
    fi
  else
    cli_errors=0
    status="$(printf '%s\n' "$line" | awk '{print $3}')"
    echo "[$now] attempt=${attempt} status=${status}"
    case "$status" in
      validating|pending|queued|running)
        : # still in flight
        ;;
      *)
        echo "RECEIPT_WAIT: terminal status=${status}"
        printf '%s\n' "$line"
        exit 0
        ;;
    esac
  fi

  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "RECEIPT_WAIT: timeout after ${MAX}s, last status=${status:-unknown}"
    exit 4
  fi
  sleep "$IVL"
done
