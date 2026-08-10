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
# and on 2026-08-10 at 04:52Z that budget turned out to be held by the shared
# account rather than by one student: the slot came free, my own rung had spent
# no attempts, and submit was still refused for 472 s. So a conflict is not
# retried blindly (it costs a shared attempt), and a rate refusal is waited out
# rather than treated as failure. Attempts are capped and each one is preceded
# by a fresh free-slot check.
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
MAX_RATE_WAITS="${MAX_RATE_WAITS:-3}"
HOLDER_POLL="${HOLDER_POLL:-10}"
DISCOVER_POLL="${DISCOVER_POLL:-90}"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# 0 = a row for this account is non-terminal, 1 = slot free, 2 = unknown.
slot_busy() { python3 "${INFLIGHT}" "$@" >/tmp/r105a-inflight.txt 2>&1; }

attempts=0
rate_waits=0
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
  raw="$(bash senpai/submit-official.sh "${BASE}" --note-file "${NOTE}" 2>&1)"
  printf '%s\n' "${raw}"
  # The CLI emits SGR colour codes even when its output is a pipe, so the id line
  # is really ESC[2m submission ESC[22m <uuid> and no ^submission anchor matches.
  out="$(printf '%s\n' "${raw}" | sed $'s/\033\\[[0-9;]*[A-Za-z]//g')"
  sid="$(printf '%s\n' "${out}" | awk '/^submission[[:space:]]/{print $2; exit}')"
  # A queued receipt that is not watched is a wasted ranked cycle, so never fall
  # through to the failure paths while the CLI is reporting success.
  if [[ -z "${sid}" ]] && printf '%s' "${out}" | grep -q 'Submission queued'; then
    sid="$(printf '%s\n' "${out}" | grep -Eio '[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}' | head -1)"
    log "id line did not parse; recovered ${sid:-nothing} from the queued receipt"
  fi
  if [[ -n "${sid}" ]]; then
    log "submitted ${sid}"
    break
  fi
  # The five-attempts-per-clock-hour submit budget belongs to the shared
  # `morganmcg1` account, not to one student, so a refusal can arrive on a rung
  # whose own attempts are untouched. The refusal names the reset delay and
  # creates no submission, so it is waited out rather than counted or fatal.
  wait_s="$(printf '%s\n' "${out}" | sed -n 's/.*Rate limit reached\. Try again in \([0-9]*\) seconds.*/\1/p' | head -1)"
  if [[ -n "${wait_s}" ]]; then
    attempts=$((attempts - 1))
    rate_waits=$((rate_waits + 1))
    if [[ "${rate_waits}" -gt "${MAX_RATE_WAITS}" ]]; then
      log "account submit budget still exhausted after ${rate_waits} waits; stopping"
      exit 1
    fi
    log "account rate limit; waiting $((wait_s + 5))s for the budget to reset"
    sleep "$((wait_s + 5))"
    continue
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

# The account index lags submission creation by a few seconds; a watcher that
# starts immediately reports "not found for this account" and exits non-zero.
sleep "${WATCH_SETTLE:-30}"

exec python3 senpai/watch-submission.py --submission "${sid}" \
  --timeout-seconds "${WATCH_TIMEOUT:-4800}"
