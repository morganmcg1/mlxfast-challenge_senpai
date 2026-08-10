#!/usr/bin/env bash
# R105-B Phase B receipt drawer.
#
# Draws exactly one receipt for one arm against a submission channel that is
# shared with other campaigns. Two hard-won constraints shape this script:
#
#   1. The API allows one submission in flight per account. A rejected
#      *conflict* attempt still consumes shared rate-limit budget, so a retry
#      loop on conflict is strictly harmful. We poll read-only and fire once
#      the channel is observed clear.
#   2. Neither the wrapper exit code nor "the newest id changed" identifies our
#      receipt, because other campaigns land rows between our poll and our
#      read. Confirmation is by a unique marker string in the note body.
#
# usage: draw.sh <arm-label> <note-file> <marker> <max-fires>

set -u

ARM="${1:?arm label}"
NOTE="${2:?note file}"
MARKER="${3:?marker}"
MAX_FIRES="${4:-2}"

BASE_SHA=1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
POLL=50
LOG="research/maple-frieren-r105b-draw-${ARM}.log"
DEADLINE=$(( $(date +%s) + 7200 ))

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

log "=== draw start arm=${ARM} head=$(git rev-parse --short HEAD) note=${NOTE} marker='${MARKER}' max_fires=${MAX_FIRES}"

channel_busy() {
  mlxfast submissions 2>/dev/null | tail -25 | grep -Eq '(validating|queued|pending|running)'
}

# Search the newest rows for our marker. Returns 0 and prints the id on a hit.
find_marker() {
  local ids id note
  ids=$(mlxfast submissions 2>/dev/null | tail -12 | awk '{print $1}' | grep -E '^[0-9a-f]{7}$')
  for id in $ids; do
    note=$(mlxfast submission-note "$id" 2>/dev/null)
    if printf '%s' "$note" | grep -qF "$MARKER"; then
      printf '%s' "$id"
      return 0
    fi
  done
  return 1
}

if hit=$(find_marker); then
  log "PRE-EXISTING receipt carries marker: id=${hit}. Nothing to draw."
  log "=== draw end arm=${ARM} result=already-present id=${hit}"
  exit 0
fi

# `fires` counts attempts that actually reached the M5, i.e. that spend the
# advisor's receipt budget. A conflict or rate-limit bounce never reaches the
# hardware, so it is logged and rate-limited against but not charged. `calls`
# bounds total wrapper invocations so a pathological channel cannot run away.
fires=0
calls=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  if channel_busy; then
    log "channel busy; waiting ${POLL}s"
    sleep "$POLL"
    continue
  fi

  if [ "$fires" -ge "$MAX_FIRES" ]; then
    log "receipt budget exhausted (${fires}/${MAX_FIRES}) without marker confirmation"
    break
  fi
  if [ "$calls" -ge 6 ]; then
    log "wrapper-invocation ceiling reached (${calls}) without marker confirmation"
    break
  fi

  calls=$((calls + 1))
  log "channel clear -> INVOKE ${calls} (charged receipts so far ${fires}/${MAX_FIRES})"
  out=$(bash senpai/submit-official.sh "$BASE_SHA" --note-file "$NOTE" 2>&1)
  rc=$?
  log "invoke ${calls} exit=${rc}"
  printf '%s\n' "$out" | sed 's/^/    | /' >>"$LOG"
  printf '%s\n' "$out" | tail -20 | sed 's/^/    | /'

  wait_s=$(printf '%s' "$out" | grep -Eo 'again in [0-9]+ seconds' | grep -Eo '[0-9]+' | head -1)
  bounced=0
  if printf '%s' "$out" | grep -qiE 'conflict|already in flight'; then
    bounced=1
    log "CONFLICT bounce: never reached M5, not charged against receipt budget"
  elif [ -n "${wait_s:-}" ]; then
    bounced=1
    log "RATE-LIMIT bounce: never reached M5, not charged against receipt budget"
  fi

  if [ "$bounced" -eq 0 ]; then
    fires=$((fires + 1))
    log "charged receipt ${fires}/${MAX_FIRES}"
    # Give the API a moment to materialise the row, then confirm by content.
    sleep 25
    if hit=$(find_marker); then
      log "CONFIRMED arm=${ARM} id=${hit}"
      log "=== draw end arm=${ARM} result=confirmed id=${hit} invocations=${calls}"
      exit 0
    fi
    log "no marker yet after receipt ${fires}"
  fi

  # A rate-limit bounce states its own wait. Honour it exactly; do not poke.
  if [ -n "${wait_s:-}" ]; then
    log "sleeping ${wait_s}s + 30s buffer"
    sleep $((wait_s + 30))
  else
    sleep "$POLL"
  fi
done

# Final confirmation sweep: the receipt may have landed while we were waiting.
for _ in 1 2 3 4 5 6; do
  if hit=$(find_marker); then
    log "CONFIRMED late arm=${ARM} id=${hit}"
    log "=== draw end arm=${ARM} result=confirmed-late id=${hit}"
    exit 0
  fi
  sleep 60
done

log "=== draw end arm=${ARM} result=unconfirmed fires=${fires}"
exit 3
