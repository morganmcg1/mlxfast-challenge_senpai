#!/bin/bash
# Self-contained arm preflight: detach to the pinned arm commit, run the scored
# local-submit preflight, stash artifacts outside the checkout, then restore the
# assignment branch. The checkout is done inside the job because a detached HEAD
# does not survive a conversation turn boundary.
# usage: run_arm_preflight.sh <ARM_LETTER> <40-char-sha>
set -u

ARM="$1"
SHA="$2"
BRANCH="maple-tanjiro/r91-ranked-base-receipt"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="/tmp/r91b"

mkdir -p "$OUT"
cd "$ROOT" || exit 1

echo "arm=${ARM} sha=${SHA} root=${ROOT} start=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
git checkout --detach "$SHA" || exit 1
git rev-parse HEAD
git status --porcelain

export PATH="${HOME}/.local/bin:${PATH}"
./benchmark.sh --local-submit > "${OUT}/arm${ARM}-local-submit.log" 2>&1
rc=$?
echo "benchmark rc=${rc} end=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$OUT/arm${ARM}-local-submit.log" "$OUT/arm${ARM}-local-submit.metrics.json" <<'PY'
import json, sys
lines = open(sys.argv[1]).read().splitlines()
starts = [i for i, l in enumerate(lines) if l.strip() == "{"]
if not starts:
    sys.exit("no json block found")
for s in starts:
    try:
        obj = json.loads("\n".join(lines[s:]))
    except Exception:
        continue
    json.dump(obj, open(sys.argv[2], "w"), indent=2, sort_keys=True)
    m = obj.get("metrics", obj)
    print("passed=%s passed_correctness=%s decode=%s prefill=%s est_score=%s commit=%s harness_hash=%s" % (
        m.get("passed"), m.get("passed_correctness"),
        m.get("decode_seconds_per_token"), m.get("prefill_seconds_per_token"),
        m.get("est_score"), m.get("commit"), m.get("harness_hash")))
    break
else:
    sys.exit("no parseable json block")
PY

git checkout "$BRANCH"
git rev-parse --abbrev-ref HEAD
exit $rc
