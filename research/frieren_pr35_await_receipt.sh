#!/bin/bash
# Block until one mlxfast submission reaches a known terminal state, then exit 0.
# Exists so the receipt wait is a supervised process instead of an interactive
# polling loop; it holds no model memory and takes no benchmark lock.
#
# Two non-obvious requirements, both learned from a false "terminal" report:
#   * `mlxfast submissions` emits ANSI colour codes even when piped, so the
#     status field must be de-escaped before any string comparison.
#   * the terminal test is fail-closed: only an explicitly recognised terminal
#     status ends the wait, so an unknown or garbled status keeps waiting
#     instead of being mistaken for a finished receipt.
#
# usage: frieren_pr35_await_receipt.sh <short-submission-id> [max-seconds] [interval-seconds]

set -uo pipefail

SUB="${1:?short submission id required}"
MAX="${2:-3300}"
IVL="${3:-60}"

deadline=$(( $(date +%s) + MAX ))
attempt=0
cli_errors=0
status=""

strip_ansi() { sed $'s/\033\\[[0-9;]*[A-Za-z]//g'; }

while :; do
  attempt=$(( attempt + 1 ))
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  line="$(mlxfast submissions 2>/dev/null | strip_ansi | grep -E "^${SUB}[[:space:]]" | tail -1)"
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
      accepted|rejected|failed|error|cancelled|canceled|invalid)
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
