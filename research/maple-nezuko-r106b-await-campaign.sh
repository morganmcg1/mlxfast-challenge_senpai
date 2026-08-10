#!/usr/bin/env bash
# R106-B: passive watcher. Blocks until the paired campaign started in an earlier
# session (a plain background shell, not a supervised job) has exited and its
# evidence sink has all expected rows, then prints a one-line summary and stops.
# It holds no GPU, no benchmark lock and no model; it exists only so the
# controller has a terminal-state event to resume the conversation on instead of
# the agent polling the sink by hand.
set -u

PID="${1:?usage: await-campaign.sh <campaign-pid> <sink> <expected-data-rows>}"
SINK="${2:?}"
WANT="${3:?}"

while kill -0 "$PID" 2>/dev/null; do
  sleep 15
done

rows=$(( $(wc -l < "$SINK") - 1 ))
echo "campaign pid ${PID} exited; ${rows} data rows in ${SINK} (expected ${WANT})"
[ "$rows" -eq "$WANT" ]
