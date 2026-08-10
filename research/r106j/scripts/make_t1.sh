#!/bin/bash
# R106-J Stage 1: build the T1 arm = advisor HEAD with the two Sources/ grants
# replaced by 4b0e051b's, using the Rule 95.6 recipe (git rm before checkout so
# files deleted in the donor tree actually disappear).
#
# Usage: make_t1.sh apply | revert
# `apply` commits the replacement on the current branch; `revert` restores the
# pre-T1 commit recorded in research/artifacts/maple-fern-r106j/t1_base.txt.

set -u
root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$root" || exit 3
art="$root/research/artifacts/maple-fern-r106j"
mkdir -p "$art"

DONOR=4b0e051bf3cd9777bd6d2be64e172c490705f9a5
ORIGIN_MAIN=1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
PATHS_T1="Sources/MLXFastModel Sources/MLXFastTransform"

case "${1:-}" in
apply)
  git rev-parse HEAD > "$art/t1_base.txt"
  git rm -r -q --ignore-unmatch -- $PATHS_T1 || exit 4
  git checkout "$DONOR" -- $PATHS_T1 || exit 5
  git add -A -- $PATHS_T1 || exit 6
  git commit -q -m "R106-J T1: replay ${DONOR:0:8} Sources/ onto advisor HEAD vendor

Co-authored-by: openhands <openhands@all-hands.dev>" || exit 7

  {
    echo "# GATE 1 (partial): git diff --numstat $DONOR HEAD -- $PATHS_T1 (MUST BE EMPTY)"
    git diff --numstat "$DONOR" HEAD -- $PATHS_T1
    echo "# GATE 1 exit=$?"
    echo "# GATE 2: origin/main ancestor of HEAD"
    git merge-base --is-ancestor "$ORIGIN_MAIN" HEAD && echo "PASS" || echo "FAIL"
    echo "# GATE 3: benchmark.json unchanged vs origin/main"
    git diff --quiet "$ORIGIN_MAIN" HEAD -- benchmark.json && echo "PASS" || echo "FAIL"
    echo "# GATE 4: git status --porcelain=v1 -uall -- \$PATHS_T1 (MUST BE EMPTY)"
    git status --porcelain=v1 --untracked-files=all -- $PATHS_T1
    echo "# GATE 4 end"
    echo "# CONTEXT: full-surface diff vs $DONOR is expected NON-empty (vendor is"
    echo "# advisor HEAD's comment-stripped copy; proven semantically identical)."
    git diff --numstat "$DONOR" HEAD -- $(jq -r '.editablePaths[]' benchmark.json) | head -60
  } > "$art/t1_gates.txt" 2>&1
  cat "$art/t1_gates.txt"
  ;;
revert)
  base=$(cat "$art/t1_base.txt") || exit 8
  git reset -q --hard "$base" || exit 9
  git rev-parse HEAD
  ;;
*)
  echo "usage: $0 apply|revert" >&2
  exit 2
  ;;
esac
