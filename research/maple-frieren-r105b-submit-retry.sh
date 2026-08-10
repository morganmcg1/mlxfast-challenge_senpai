#!/bin/bash
# Official submission with throttle-aware retry.
# Usage: r105b-submit-retry3.sh <base_sha> <note_file> <label> <marker>
# Success is confirmed ONLY by finding <marker> in a recent submission's public
# note. A changed submission id is NOT sufficient: the account is shared with
# other campaign roles and their submissions also change the tail.
set -u
BASE_SHA="$1"; NOTE="$2"; LABEL="$3"; MARKER="$4"
cd /Users/ec2-user/.senpai/native/mlxfast-maple-20260804/roles/student-maple-frieren/workspace/target || exit 1
export PATH="${HOME}/.local/bin:${PATH}"

recent_ids() { mlxfast submissions 2>/dev/null | tail -6 | awk '{print $1}'; }
mine() {
  local id
  for id in $(recent_ids); do
    if mlxfast submission-note "$id" 2>/dev/null | grep -q "$MARKER"; then
      echo "$id"
      return 0
    fi
  done
  return 1
}

echo "[$LABEL] head=$(git rev-parse HEAD) base=$BASE_SHA note=$NOTE marker=$MARKER"
echo "[$LABEL] line 701: $(sed -n '701p' Sources/MLXFastModel/LagunaRuntimeModel.swift)"
echo "[$LABEL] recent submissions before: $(recent_ids | tr '\n' ' ')"
if id="$(mine)"; then
  echo "[$LABEL] ALREADY PRESENT: submission $id already carries the marker; nothing to do"
  exit 0
fi

for i in $(seq 1 40); do
  echo "=== [$LABEL] attempt $i at $(date -u +%H:%M:%SZ) ==="
  out="$(bash senpai/submit-official.sh "$BASE_SHA" --note-file "$NOTE" 2>&1)"
  echo "$out" | tail -6

  sleep 15
  if id="$(mine)"; then
    echo "[$LABEL] ACCEPTED: submission $id at $(date -u +%H:%M:%SZ)"
    exit 0
  fi

  secs="$(echo "$out" | sed -n 's/.*Try again in \([0-9]*\) seconds.*/\1/p' | tail -1)"
  if [ -n "$secs" ]; then
    wait=$((secs + 20))
    echo "[$LABEL] rate limited; sleeping ${wait}s"
    sleep "$wait"
    continue
  fi

  if echo "$out" | grep -q 'in flight for this benchmark'; then
    echo "[$LABEL] slot busy (another role holds it); sleeping 120s"
    sleep 120
    continue
  fi

  echo "[$LABEL] unrecognised outcome; sleeping 120s then retrying"
  sleep 120
done

echo "[$LABEL] EXHAUSTED without confirming a submission carrying the marker"
exit 4
