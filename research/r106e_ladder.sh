#!/usr/bin/env bash
# R106-E / Rule 95.7 draw ladder -- the continuous-draw driver.
#
#   Usage:  research/r106e_ladder.sh FIRST LAST [IDLE_DEADLINE_MIN]
#   e.g.    research/r106e_ladder.sh 04 13
#
# Rule 95.7 says: replay the 4b0e051b family under the 95.6 recipe and draw it
# continuously until the record or the deadline, ONE SUBMISSION AT A TIME under
# Rule 88's watch-until-idle protocol.  This script is exactly that loop and
# nothing more.  Per leg it does:
#
#   1. research/r106e_draw.sh NN      -- re-stamp the dedup marker, re-verify
#                                        the Rule 95.6 gates, commit.  The tree
#                                        never changes; only one comment line.
#   2. channel idle watch             -- block until OUR account has no
#                                        non-terminal submission.  This is also
#                                        what makes leg NN wait for leg NN-1's
#                                        receipt, so the ladder is serial by
#                                        construction.
#   3. exactly ONE submit attempt.
#   4. idle watch again + harvest     -- wait for our own receipt, then decode
#                                        it into (cs, f).
#
# Safety rails, in order of importance:
#   * a deadline exit (2) from the idle watch NEVER submits -- we stop instead;
#     firing into a busy queue burns the limiter for nothing (#597 13.3).
#   * a submit failure is retried at most twice, and only after re-establishing
#     idle; three strikes stops the ladder for human adjudication.
#   * if any harvested receipt beats the record the ladder stops immediately so
#     the result can be reported rather than buried under further draws.
set -uo pipefail

FIRST="${1:?usage: $0 FIRST LAST [IDLE_DEADLINE_MIN]}"
LAST="${2:?usage: $0 FIRST LAST [IDLE_DEADLINE_MIN]}"
IDLE_MIN="${3:-90}"

MAIN="1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7"
NOTE="research/maple-frieren-r106e-draw-note.md"
IDLE="research/advisor_r106_channel_idle_watch.py"
HARVEST="research/maple-frieren-r107-harvest.py"

cd "$(git rev-parse --show-toplevel)"

banner() { printf '\n========== %s ==========\n' "$*"; }

# Bring the receipt ledger up to date before adding to it, so the log opens
# with the true state of the ladder rather than my assumption about it.
banner "opening harvest"
python3 "$HARVEST" --last 20
if [[ $? -eq 4 ]]; then
  echo "record already beaten before this ladder started -- stopping." >&2
  exit 4
fi

for n in $(seq -w "$FIRST" "$LAST"); do
  banner "LEG $n  prepare"
  if ! bash research/r106e_draw.sh "$n"; then
    echo "LEG $n: draw preparation failed -- stopping the ladder." >&2
    exit 1
  fi

  attempt=0
  submitted=0
  while [[ $attempt -lt 3 && $submitted -eq 0 ]]; do
    attempt=$((attempt + 1))
    banner "LEG $n  wait for idle channel (attempt $attempt)"
    python3 "$IDLE" --poll 45 --deadline-min "$IDLE_MIN" --require-idle-polls 2
    rc=$?
    if [[ $rc -ne 0 ]]; then
      echo "LEG $n: idle watch exited $rc (2 = deadline while busy)." >&2
      echo "Refusing to submit into a busy queue.  Ladder stops here." >&2
      exit $rc
    fi

    banner "LEG $n  SUBMIT"
    if senpai/submit-official.sh "$MAIN" --note-file "$NOTE"; then
      submitted=1
    else
      echo "LEG $n: submit attempt $attempt failed; backing off 300 s." >&2
      sleep 300
    fi
  done
  if [[ $submitted -eq 0 ]]; then
    echo "LEG $n: three failed submit attempts -- stopping for adjudication." >&2
    exit 1
  fi

  banner "LEG $n  wait for our own receipt"
  python3 "$IDLE" --poll 60 --deadline-min 120 --require-idle-polls 2
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "LEG $n: receipt wait exited $rc; harvesting anyway." >&2
  fi

  banner "LEG $n  harvest"
  python3 "$HARVEST" --last 20
  hrc=$?
  if [[ $hrc -eq 4 ]]; then
    echo "LEG $n: RECORD BEATEN -- stopping the ladder." >&2
    exit 4
  fi
done

banner "ladder complete: legs $FIRST..$LAST"
