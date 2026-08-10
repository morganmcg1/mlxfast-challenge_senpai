#!/bin/bash
# R106-E single-shot draw launcher.
#
# Protocol (rev3, Rule 88): watch until the official validation queue is IDLE,
# then fire EXACTLY ONE submit, then stop. There is no retry. If the watcher
# hits its deadline while the queue is still busy this script exits without
# submitting and the caller must invoke it again deliberately.
set -u

REPO="/Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target"
BASE_SHA="1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7"
NOTE="$1"
DEADLINE_MIN="${2:-27}"

cd "$REPO" || exit 3

echo "[draw] HEAD=$(git rev-parse HEAD)"
echo "[draw] note=$NOTE"

DIRTY="$(git status --porcelain=v1 --untracked-files=all | head -5)"
if [ -n "$DIRTY" ]; then
  echo "[draw] ABORT: worktree not clean"
  echo "$DIRTY"
  exit 4
fi

IDENT="$(git diff --numstat 7491001264832c2566de65c5cab9f363c6426e09 HEAD -- Sources Vendor)"
if [ -n "$IDENT" ]; then
  echo "[draw] ABORT: Sources/Vendor differ from the research base"
  echo "$IDENT"
  exit 5
fi
echo "[draw] tree identity vs base: clean"

echo "[draw] watching for an idle channel (deadline ${DEADLINE_MIN}m)..."
python3 research/advisor_r106_channel_idle_watch.py \
  --poll 60 --deadline-min "$DEADLINE_MIN" --require-idle-polls 2
WATCH=$?
echo "[draw] watcher exit=$WATCH"

if [ "$WATCH" -ne 0 ]; then
  echo "[draw] queue still busy at deadline; NOT submitting. Re-invoke deliberately."
  exit 2
fi

echo "[draw] channel idle at $(date -u +%Y-%m-%dT%H:%M:%SZ); firing exactly one submit"
bash senpai/submit-official.sh "$BASE_SHA" --note-file "$NOTE"
RC=$?
echo "[draw] submit-official.sh rc=$RC at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "$RC"
