#!/bin/bash
# Self-managed submission dispatcher for PR #137 (maple-fern), version 3.
#
# Complies with senpai/program.md @ f13d659 ("Let submitters manage validation
# retries"): no central queue owner; the submitter owns its candidate's
# lifecycle, preserves the exact commit and note, rechecks periodically without
# a tight polling loop, honours server retry guidance, and never duplicates a
# submission that is already queued or validating.
#
# History.
#   v1 retried `mlxfast submit` every 180 s and let the server arbitrate
#     capacity. Race-free but expensive: 18 uploads in 52 min tripped a server
#     rate limit ("Try again in 1914 seconds") that was not whitelisted.
#   v2 split the concerns: a read-only feed poll every 120 s decided *when* to
#     submit. Submit calls fell to ~4/hour, but the feed read costs 8.3 MB
#     gzipped and the 120 s cadence means ~60 s mean detection latency. The
#     in-flight limit is one submission per *solver account* and several Senpai
#     campaigns share this account, so a freed slot is contested: on
#     2026-08-06 the previous holder went terminal at 23:08:00Z and another
#     campaign had claimed the slot by 23:08:38Z, 38 s later. v2 cannot win a
#     38 s race from a 120 s poll.
#   v3 adds a cheap watch tier. Discovery still reads the feed, but only to
#     learn the id of the row that is blocking this account. That row is then
#     polled through `GET /api/submissions/<id>`, which returns the same record
#     in 13.6 KB in ~0.6 s instead of 17.3 MB in ~3 s. Watching at 5 s costs
#     ~9.8 MB/hour against ~248 MB/hour for a 120 s feed poll, so v3 is both
#     ~25x lighter on the server and ~24x faster to notice a freed slot:
#     ~2.5 s mean detection plus ~11 s upload, inside the observed 38 s race.
#
# Submit attempts stay rare: at most one per observed transition, with a hard
# MIN_GAP floor, plus one forced attempt every FORCE seconds so a misread
# status cannot stall the dispatcher.
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
INFLIGHT="${INFLIGHT:-/tmp/pr137_submit/inflight3.py}"  # research/maple-fern-submit-inflight.py

WATCH_POLL=5     # single-row recheck while a known row blocks the account
FEED_POLL=30     # backoff after an unknown/errored read
REDISCOVER=900   # re-read the feed even while watching, in case the watch is stale
FORCE=1800       # submit at least this often even when status looks occupied
FREE_GAP=45      # floor between attempts that a *detected* free slot triggers
BLIND_GAP=240    # floor between attempts that only the forced timer triggers
LIED_MAX=3       # consecutive "feed said free, server said busy" before cooldown
LIED_COOLDOWN=900
BUDGET=10200     # under the 10800 s supervised-launch ceiling
NOT_BEFORE=0     # raised only by explicit server rate-limit guidance

cd "$TGT" || exit 70

echo "=== retry_submit v3 start $(date -u +%FT%TZ) ==="
echo "HEAD: $(git rev-parse HEAD)"
echo "worktree: $(git status --porcelain | wc -l | tr -d ' ') modified path(s)"
echo "note: $NOTE ($(wc -c <"$NOTE" | tr -d ' ') bytes)"
echo "watch: ${WATCH_POLL}s  rediscover: ${REDISCOVER}s  forced submit: ${FORCE}s  budget: ${BUDGET}s"

START=$(date +%s)
last_submit=0        # 0 until the first attempt, so a real transition is never gated
force_base=$START
last_discover=0
attempt=0
poll=0
lied=0
watch_id=""

while :; do
  now=$(date +%s)
  left=$((BUDGET - (now - START)))
  if [ "$left" -le 0 ]; then
    echo
    echo "=== budget exhausted after ${attempt} submit attempt(s); nothing created ==="
    exit 75
  fi

  # A hold window plus a free account is the one state that would otherwise
  # re-read the whole feed on every tick for no possible action.
  if [ "$now" -lt "$NOT_BEFORE" ] && [ -z "$watch_id" ]; then
    nap=$((NOT_BEFORE - now))
    [ "$nap" -gt 120 ] && nap=120
    echo "hold window: $(((NOT_BEFORE - now) / 60)) min left; sleeping ${nap}s"
    sleep "$nap"
    continue
  fi

  if [ -n "$watch_id" ] && [ $((now - last_discover)) -ge "$REDISCOVER" ]; then
    echo "--- rediscovering (watch older than $((REDISCOVER / 60)) min) ---"
    watch_id=""
  fi

  if [ -n "$watch_id" ]; then
    status_out=$("$INFLIGHT" "$watch_id" 2>&1)
    status_rc=$?
  else
    status_out=$("$INFLIGHT" 2>&1)
    status_rc=$?
    last_discover=$now
  fi
  poll=$((poll + 1))

  case "$status_rc" in
    0)  # still blocked; make sure we are watching the blocking row
      lied=0
      if [ -z "$watch_id" ]; then
        watch_id=$(printf '%s\n' "$status_out" | awk '/^inflight /{print $2; exit}')
        echo
        echo "--- poll $poll at $(date -u +%FT%TZ) (budget left: $((left / 60)) min) ---"
        echo "$status_out"
        if [ -n "$watch_id" ]; then
          echo "watching $watch_id every ${WATCH_POLL}s"
        else
          echo "blocked but no row id parsed; falling back to the ${FEED_POLL}s feed poll"
        fi
      fi
      ;;
    1)
      echo
      echo "--- poll $poll at $(date -u +%FT%TZ) (budget left: $((left / 60)) min) ---"
      echo "$status_out"
      echo "account free"
      watch_id=""
      ;;
    *)
      echo
      echo "--- poll $poll at $(date -u +%FT%TZ) (budget left: $((left / 60)) min) ---"
      echo "$status_out"
      echo "status unknown; backing off ${FEED_POLL}s"
      watch_id=""
      sleep "$FEED_POLL"
      continue
      ;;
  esac

  now=$(date +%s)
  gap=$((last_submit == 0 ? 1 << 30 : now - last_submit))
  try=0
  if [ "$now" -lt "$NOT_BEFORE" ]; then
    [ "$status_rc" -eq 1 ] && echo "hold window: $(((NOT_BEFORE - now) / 60)) min left; not submitting"
  elif [ "$status_rc" -eq 1 ] && [ "$gap" -ge "$FREE_GAP" ]; then
    try=1
  elif [ "$status_rc" -eq 1 ]; then
    echo "free-gap: only ${gap}s since the last attempt; holding"
  elif [ $((now - force_base)) -ge "$FORCE" ] && [ "$gap" -ge "$BLIND_GAP" ]; then
    echo "forced attempt ($(((now - force_base) / 60)) min since the last one)"
    try=1
  fi

  if [ "$try" -eq 1 ]; then
    attempt=$((attempt + 1))
    last_submit=$now
    force_base=$now
    echo "--- submit attempt $attempt at $(date -u +%FT%TZ) ---"
    out=$(mlxfast submit --model "senpai" --note-file "$NOTE" 2>&1)
    rc=$?
    echo "$out"
    echo "--- submit exit $rc at $(date -u +%FT%TZ) ---"

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
    elif printf '%s' "$out" | grep -q 'submission(s) in flight'; then
      watch_id=""
      if [ "$status_rc" -eq 1 ]; then
        lied=$((lied + 1))
        echo "lost the slot (feed said free, server says busy; streak $lied)"
        if [ "$lied" -ge "$LIED_MAX" ]; then
          NOT_BEFORE=$((now + LIED_COOLDOWN))
          lied=0
          echo "feed disagrees repeatedly; cooling down until $(date -u -r "$NOT_BEFORE" +%FT%TZ)"
        fi
      else
        echo "forced attempt confirmed the account is busy"
      fi
    else
      echo
      echo "=== non-conflict response; stopping without retry (a submission may exist) ==="
      exit "$rc"
    fi
  fi

  if [ -n "$watch_id" ]; then
    sleep "$WATCH_POLL"
  else
    sleep "$FEED_POLL"
  fi
done
