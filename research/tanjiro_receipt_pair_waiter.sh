#!/bin/bash
# Supervise the H16 ranked receipt pair: wait for the already-dispatched ARM to
# reach a terminal state, then dispatch the byte-exact CONTROL from the base
# worktree and wait for it too. Exists so the receipt pair is driven by one
# supervised process instead of interactive polling.
#
#   ARM_ID          short id of the in-flight arm submission (required)
#   CONTROL_DIR     worktree pinned to the base commit (required)
#   CONTROL_NOTE    note file for the control submission (required)
#   ARM_WAIT_S      seconds to wait for the arm       (default 4800)
#   QUEUE_WAIT_S    seconds to wait for a free slot   (default 3600)
#   CTL_WAIT_S      seconds to wait for the control   (default 5400)

export PATH="${HOME}/.local/bin:${PATH}"

ARM_ID="${ARM_ID:?ARM_ID required}"
CONTROL_DIR="${CONTROL_DIR:?CONTROL_DIR required}"
CONTROL_NOTE="${CONTROL_NOTE:?CONTROL_NOTE required}"
ARM_WAIT_S="${ARM_WAIT_S:-4800}"
QUEUE_WAIT_S="${QUEUE_WAIT_S:-3600}"
CTL_WAIT_S="${CTL_WAIT_S:-5400}"
POLL_S=60
QUEUE_POLL_S=45

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# The CLI colourises the status column, so the escapes must go before any
# field comparison; without this every state compares unequal and the waiter
# would treat a finished submission as still running.
subs() { mlxfast submissions 2>/dev/null | sed -E $'s/\033\\[[0-9;]*m//g'; }

row_for() { subs | awk -v id="$1" '$1 ~ id {r=$0} END{print r}'; }
state_for() { row_for "$1" | awk '{print $3}'; }

# A submission is terminal once it is no longer queued or being measured.
is_terminal() {
  case "$1" in
    validating|running|pending|queued|measuring|"") return 1 ;;
    *) return 0 ;;
  esac
}

queue_busy() {
  subs | awk '
    $3=="validating"||$3=="running"||$3=="pending"||$3=="queued"||$3=="measuring" {n++}
    END{exit (n>0)?0:1}'
}

wait_terminal() { # id, budget
  local id="$1" budget="$2" waited=0 st
  while [ "$waited" -lt "$budget" ]; do
    st="$(state_for "$id")"
    if is_terminal "$st"; then
      log "$id terminal: $st"
      return 0
    fi
    log "$id state=${st:-<absent>} (${waited}s/${budget}s)"
    sleep "$POLL_S"
    waited=$((waited + POLL_S))
  done
  log "$id STILL NOT TERMINAL after ${budget}s"
  return 1
}

echo "===== ARM: $ARM_ID ====="
wait_terminal "$ARM_ID" "$ARM_WAIT_S"; arm_ok=$?
echo "ARM_ROW: $(row_for "$ARM_ID")"
if [ "$arm_ok" -ne 0 ]; then
  echo "RESULT: arm did not finish in budget; control NOT dispatched"
  exit 2
fi

echo "===== CONTROL dispatch ====="
[ -f "$CONTROL_NOTE" ] || { echo "RESULT: missing note $CONTROL_NOTE"; exit 3; }
cd "$CONTROL_DIR" || { echo "RESULT: bad CONTROL_DIR"; exit 3; }
log "control worktree HEAD $(git rev-parse HEAD)"

# The in-flight slot is shared with another track, so wait for it rather than
# racing; a refused submit still exits 0, so the id is parsed from stdout.
ctl_id=""
qwaited=0
while [ "$qwaited" -lt "$QUEUE_WAIT_S" ]; do
  if queue_busy; then
    log "queue busy (${qwaited}s/${QUEUE_WAIT_S}s)"
    sleep "$QUEUE_POLL_S"
    qwaited=$((qwaited + QUEUE_POLL_S))
    continue
  fi
  log "queue clear, submitting control (${qwaited}s waited)"
  out="$(mlxfast submit --model "senpai" --note-file "$CONTROL_NOTE" 2>&1)"
  echo "$out"
  ctl_id="$(echo "$out" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)"
  [ -n "$ctl_id" ] && break
  log "no submission id parsed, retrying"
  sleep "$QUEUE_POLL_S"
  qwaited=$((qwaited + QUEUE_POLL_S))
done

if [ -z "$ctl_id" ]; then
  echo "RESULT: control was never accepted"
  exit 4
fi
echo "CONTROL_ID: $ctl_id"

echo "===== CONTROL wait ====="
wait_terminal "${ctl_id:0:7}" "$CTL_WAIT_S"; ctl_ok=$?
echo "ARM_ROW: $(row_for "$ARM_ID")"
echo "CONTROL_ROW: $(row_for "${ctl_id:0:7}")"
[ "$ctl_ok" -eq 0 ] && echo "RESULT: pair complete" || echo "RESULT: control not terminal in budget"
exit 0
