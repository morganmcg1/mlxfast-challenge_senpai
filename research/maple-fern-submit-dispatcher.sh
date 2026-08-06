#!/bin/bash
# Self-managed submission dispatcher for PR #137 (maple-fern), version 2.
#
# Complies with senpai/program.md @ f13d659 ("Let submitters manage validation
# retries"): no central queue owner; the submitter owns its candidate's
# lifecycle, preserves the exact commit and note, rechecks periodically without
# a tight polling loop, honours server retry guidance, and never duplicates a
# submission that is already queued or validating.
#
# Why this shape. v1 retried `mlxfast submit` every 180 s so the server itself
# arbitrated capacity. That is race-free but expensive: 18 upload attempts in
# 52 min tripped a server rate limit ("Try again in 1914 seconds"), which was
# not whitelisted, so the loop stopped. v2 separates the two concerns:
#   * a cheap read-only status poll decides *when* to try, and
#   * `submit` runs only when this account looks free, plus one forced attempt
#     every FORCE seconds so a misread status cannot stall the dispatcher.
# Submit calls drop from ~20/hour to at most ~4/hour, while the poll-to-submit
# race window shrinks from 180 s to a few seconds.
#
# Safety: only the in-flight conflict and an explicit rate limit are retried.
# Any other non-zero response may have created a submission, so the script
# stops immediately rather than risk duplicating a queued candidate.
#
# Exit 0  = submission accepted (id printed)
# Exit 75 = budget exhausted, capacity never cleared; nothing was created
# other   = ambiguous or hard failure; do NOT retry without inspecting first

set -u
export PATH="${HOME}/.local/bin:${PATH}"

TGT="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-fern/workspace/target"
NOTE="research/maple-fern-pr137-submission-note.md"
INFLIGHT="${INFLIGHT:-/tmp/pr137_submit/inflight.py}"   # research/maple-fern-submit-inflight.py

POLL=120         # status recheck cadence against a read-only endpoint
FORCE=900        # submit at least this often even when status looks occupied
BUDGET=10200     # under the 10800 s supervised-launch ceiling
NOT_BEFORE=1786057260   # 2026-08-06T23:01:00Z = rate limit at 22:28:04Z + 1914 s

cd "$TGT" || exit 70

echo "=== retry_submit v2 start $(date -u +%FT%TZ) ==="
echo "HEAD: $(git rev-parse HEAD)"
echo "worktree: $(git status --porcelain | wc -l | tr -d ' ') modified path(s)"
echo "note: $NOTE ($(wc -c <"$NOTE" | tr -d ' ') bytes)"
echo "poll: ${POLL}s   forced submit: ${FORCE}s   budget: ${BUDGET}s"
echo "not before: $(date -u -r "$NOT_BEFORE" +%FT%TZ) (server rate-limit guidance)"

START=$(date +%s)
last_submit=0
attempt=0
poll=0

while :; do
  now=$(date +%s)
  left=$((BUDGET - (now - START)))
  if [ "$left" -le 0 ]; then
    echo
    echo "=== budget exhausted after ${attempt} submit attempt(s); nothing created ==="
    exit 75
  fi

  poll=$((poll + 1))
  status_out=$("$INFLIGHT" 2>&1)
  status_rc=$?
  echo
  echo "--- poll $poll at $(date -u +%FT%TZ) (budget left: $((left / 60)) min, rc=$status_rc) ---"
  echo "$status_out"

  now=$(date +%s)
  try=0
  if [ "$now" -lt "$NOT_BEFORE" ]; then
    echo "rate-limit window: $(((NOT_BEFORE - now) / 60)) min left; not submitting"
  elif [ "$status_rc" -eq 1 ]; then
    echo "account free; submitting"
    try=1
  elif [ $((now - last_submit)) -ge "$FORCE" ]; then
    echo "forced attempt ($(((now - last_submit) / 60)) min since the last one)"
    try=1
  fi

  if [ "$try" -eq 1 ]; then
    attempt=$((attempt + 1))
    last_submit=$now
    echo "--- submit attempt $attempt at $(date -u +%FT%TZ) ---"
    out=$(mlxfast submit --model "senpai" --note-file "$NOTE" 2>&1)
    rc=$?
    echo "$out"
    echo "--- submit exit $rc ---"

    if [ "$rc" -eq 0 ]; then
      echo
      echo "=== submission accepted at $(date -u +%FT%TZ) after ${attempt} attempt(s) ==="
      exit 0
    fi

    if printf '%s' "$out" | grep -qi 'rate limit'; then
      secs=$(printf '%s' "$out" | grep -Eio 'try again in ([0-9]+) second' | grep -Eo '[0-9]+' | head -1)
      [ -n "${secs:-}" ] || secs=1920
      NOT_BEFORE=$((now + secs + 30))
      echo "rate limited; next submit not before $(date -u -r "$NOT_BEFORE" +%FT%TZ)"
    elif ! printf '%s' "$out" | grep -q 'submission(s) in flight'; then
      echo
      echo "=== non-conflict response; stopping without retry (a submission may exist) ==="
      exit "$rc"
    fi
  fi

  sleep "$POLL"
done
