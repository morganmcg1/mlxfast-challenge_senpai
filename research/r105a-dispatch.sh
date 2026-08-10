#!/bin/bash
# Dispatch exactly one r105-A ladder rung and watch it to a terminal verdict.
#
#   research/r105a-dispatch.sh <base_sha> <note-file>
#
# The shared `morganmcg1` account permits one in-flight submission per
# benchmark, and several Senpai students contend for that slot. On 2026-08-10 a
# sibling claimed it 4 s before my own receipt went terminal, so an agent that
# checks the queue in one conversation turn and submits in the next always
# loses the handoff. This watches the current holder by id (13.6 KB per read
# against 17.3 MB for a feed read) and submits within seconds of it clearing.
#
# `mlxfast submit` is separately rate limited to five attempts per clock hour,
# so a conflict is not retried blindly: it costs an attempt, and an exhausted
# budget at the moment the slot opens costs a whole 25-minute cycle. Attempts
# are capped and each one is preceded by a fresh free-slot check.
#
# Idempotency: submit is invoked at most once successfully; after that the
# script only polls, so re-running the job cannot spend two receipts.
set -u
cd "$(dirname "$0")/.." || exit 1
export PATH="${HOME}/.local/bin:${PATH}"

BASE="${1:?usage: r105a-dispatch.sh <base_sha> <note-file>}"
NOTE="${2:?usage: r105a-dispatch.sh <base_sha> <note-file>}"
INFLIGHT=research/maple-fern-submit-inflight.py
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
HOLDER_POLL="${HOLDER_POLL:-10}"
DISCOVER_POLL="${DISCOVER_POLL:-90}"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# 0 = a row for this account is non-terminal, 1 = slot free, 2 = unknown.
slot_busy() { python3 "${INFLIGHT}" "$@" >/tmp/r105a-inflight.txt 2>&1; }

attempts=0
ready=0
while :; do
  # A discovery read costs a 17.3 MB feed fetch, so once a holder is known to
  # have gone terminal the slot is claimed without re-reading the feed: the
  # fetch itself is long enough to lose the handoff to a sibling agent.
  if [[ "${ready}" -eq 0 ]]; then
    slot_busy
    case $? in
      1) log "slot free" ;;
      0)
        holder="$(awk '/^inflight /{print $2; exit}' /tmp/r105a-inflight.txt)"
        log "slot held by ${holder:-unknown}; waiting"
        if [[ -n "${holder}" ]]; then
          while :; do
            sleep "${HOLDER_POLL}"
            slot_busy "${holder}"
            [[ $? -eq 0 ]] || break
          done
          log "holder ${holder} is terminal; racing for the slot"
          ready=1
        else
          sleep "${DISCOVER_POLL}"
        fi
        continue
        ;;
      *)
        log "in-flight state unknown, treating as busy: $(cat /tmp/r105a-inflight.txt)"
        sleep "${DISCOVER_POLL}"
        continue
        ;;
    esac
  fi
  ready=0

  attempts=$((attempts + 1))
  log "submit attempt ${attempts}/${MAX_ATTEMPTS}"
  out="$(bash senpai/submit-official.sh "${BASE}" --note-file "${NOTE}" 2>&1)"
  printf '%s\n' "${out}"
  # A queued submission prints `submission  <uuid>` on its own line.
  sid="$(printf '%s\n' "${out}" | awk '/^submission[[:space:]]/{print $2; exit}')"
  if [[ -n "${sid}" ]]; then
    log "submitted ${sid}"
    break
  fi
  if ! printf '%s' "${out}" | grep -q '"code":"conflict"'; then
    log "submit failed for a reason other than the in-flight limit; stopping"
    exit 1
  fi
  if [[ "${attempts}" -ge "${MAX_ATTEMPTS}" ]]; then
    log "hourly submit-attempt budget spent without winning the slot; stopping"
    exit 1
  fi
  sleep "${DISCOVER_POLL}"
done

exec python3 senpai/watch-submission.py --submission "${sid}" \
  --timeout-seconds "${WATCH_TIMEOUT:-4800}"
