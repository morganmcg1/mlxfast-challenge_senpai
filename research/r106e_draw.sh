#!/usr/bin/env bash
# R106-E / Rule 95.7 draw-ladder leg preparation.
#
# Usage:  research/r106e_draw.sh NN
#
# Prepares leg NN of the fixed-tree draw ladder:
#   * rewrites the single dedup marker comment at the end of
#     Sources/MLXFastModel/LagunaRuntimeModel.swift,
#   * rewrites the marker string inside the public note,
#   * re-verifies the Rule 95.6 gates (2/3/4) and proves the *only* change
#     under editablePaths since the previous leg is that one comment line,
#   * commits, and prints the Rule 75 surface identity.
#
# It never submits.  Submission is a separate, deliberate step.
set -euo pipefail

NN="${1:?usage: $0 NN}"
MARKER="senpai-r106e-replay-${NN}"
FILE="Sources/MLXFastModel/LagunaRuntimeModel.swift"
NOTE="research/maple-frieren-r106e-draw-note.md"
MAIN="1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7"
FAMILY="4b0e051bf3cd9777bd6d2be64e172c490705f9a5"

cd "$(git rev-parse --show-toplevel)"
PATHS=$(jq -r '.editablePaths[]' benchmark.json)

prev_head="$(git rev-parse HEAD)"

# --- 1. the one-line perturbation -------------------------------------------
python3 - "$FILE" "$MARKER" <<'PY'
import re, sys
path, marker = sys.argv[1], sys.argv[2]
src = open(path, encoding="utf-8").read()
new, n = re.subn(r"// senpai-[A-Za-z0-9._-]+\n?\Z", "// %s\n" % marker, src)
if n != 1:
    sys.exit("marker comment not found exactly once at end of %s" % path)
open(path, "w", encoding="utf-8").write(new)
PY

python3 - "$NOTE" "$MARKER" <<'PY'
import re, sys
path, marker = sys.argv[1], sys.argv[2]
src = open(path, encoding="utf-8").read()
new, n = re.subn(r"(R106E-REPLAY-DRAW-\S+|senpai-r106e-replay-\S+|senpai-r93-null-1)",
                 marker, src)
if n == 0:
    sys.exit("no marker placeholder found in %s" % path)
open(path, "w", encoding="utf-8").write(new)
print("note: rewrote %d marker occurrence(s)" % n)
PY

# --- 2. prove the perturbation is exactly one comment line ------------------
echo "=== changed files under editablePaths since ${prev_head:0:8} ==="
git --no-pager diff --numstat -- $PATHS
nfiles=$(git diff --numstat -- $PATHS | wc -l | tr -d ' ')
adds=$(git diff --numstat -- $PATHS | awk '{a+=$1} END{print a+0}')
dels=$(git diff --numstat -- $PATHS | awk '{a+=$2} END{print a+0}')
if [[ "$nfiles" != "1" || "$adds" != "1" || "$dels" != "1" ]]; then
  echo "ABORT: expected exactly 1 file / +1 / -1, got $nfiles / +$adds / -$dels" >&2
  exit 1
fi
echo "--- the diff itself ---"
git --no-pager diff -U0 -- "$FILE"

git add -A -- $PATHS "$NOTE"
git commit -q -m "R106-E draw ${NN}: dedup marker ${MARKER} on the 4b0e051b surface"

# --- 3. Rule 95.6 gates ------------------------------------------------------
echo "=== GATE 2 base ancestry ==="
git merge-base --is-ancestor "$MAIN" HEAD && echo "PASS"
echo "=== GATE 3 harness untouched ==="
git diff --quiet "$MAIN" HEAD -- benchmark.json && echo "PASS"
echo "=== GATE 4 worktree clean under editablePaths ==="
st=$(git status --porcelain -u all -- $PATHS); [[ -z "$st" ]] && echo "PASS" || { echo "$st"; exit 1; }
echo "=== GATE 1' surface vs family tree ${FAMILY:0:8} (must be the marker line only) ==="
git --no-pager diff --numstat "$FAMILY" HEAD -- $PATHS

# --- 4. Rule 75 surface identity --------------------------------------------
list=$(mktemp)
git ls-files -- $PATHS > "$list"
bytes=$(xargs stat -f %z < "$list" | awk '{s+=$1} END{print s}')
sha=$(sort "$list" | xargs shasum -a 256 | shasum -a 256 | awk '{print $1}')
echo "=== Rule 75 surface identity ==="
echo "files:  $(wc -l < "$list" | tr -d ' ')"
echo "bytes:  $bytes"
echo "sha256: $sha"
echo "HEAD:   $(git rev-parse HEAD)"
rm -f "$list"
