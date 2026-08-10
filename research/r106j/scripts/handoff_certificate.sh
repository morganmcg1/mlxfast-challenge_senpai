#!/bin/bash
# Stage-3 handoff certificate: capture, on the exact current HEAD, every mechanical
# item frieren needs before spending the single remaining official draw.
# Read-only with respect to the working tree. bash 3.2 compatible.
#
# Usage: research/r106j/scripts/handoff_certificate.sh [BASE_SHA]

set -uo pipefail

BASE_SHA="${1:-446fe9875d1f95b1216628b5809a99da844e5c79}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="research/artifacts/maple-fern-r106j"
mkdir -p "$OUT_DIR"
OUT="${HANDOFF_OUT:-$OUT_DIR/handoff_certificate.txt}"

git fetch --quiet origin main
MAIN_SHA="$(git rev-parse FETCH_HEAD)"
HEAD_SHA="$(git rev-parse HEAD)"

{
  echo "=== Stage-3 handoff certificate ==="
  echo "generated_utc   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "repo_root       $REPO_ROOT"
  echo "BASE_SHA        $BASE_SHA"
  echo "HEAD            $HEAD_SHA"
  echo "origin/main     $MAIN_SHA   (freshly fetched)"
  echo

  echo "=== precondition 1 — BASE_SHA is an ancestor of HEAD ==="
  echo "\$ git merge-base --is-ancestor $BASE_SHA HEAD"
  git merge-base --is-ancestor "$BASE_SHA" HEAD; echo "exit=$?  (0 == pass)"
  echo

  echo "=== precondition 2 — benchmark.json identical: origin/main vs BASE_SHA ==="
  echo "\$ git diff --quiet $MAIN_SHA $BASE_SHA -- benchmark.json"
  git diff --quiet "$MAIN_SHA" "$BASE_SHA" -- benchmark.json; echo "exit=$?  (0 == pass)"
  echo

  echo "=== precondition 3 — benchmark.json identical: origin/main vs HEAD ==="
  echo "\$ git diff --quiet $MAIN_SHA HEAD -- benchmark.json"
  git diff --quiet "$MAIN_SHA" HEAD -- benchmark.json; echo "exit=$?  (0 == pass)"
  echo

  echo "=== precondition 4 — benchmark.json carries no uncommitted/untracked/ignored state ==="
  echo "\$ git status --porcelain=v1 --untracked-files=all --ignored=matching -- benchmark.json"
  git status --porcelain=v1 --untracked-files=all --ignored=matching -- benchmark.json
  echo "(no lines above == pass)"
  echo

  echo "=== no skip-worktree / assume-unchanged anywhere in the index ==="
  echo "\$ git ls-files -v | awk '\$1 != \"H\"'"
  git ls-files -v | awk '$1 != "H"'
  echo "(no lines above == pass)"
  echo

  echo "=== submission surface is committed and clean ==="
  echo "\$ git status --porcelain=v1 --untracked-files=all -- <editablePaths>"
  jq -r '.editablePaths[]' benchmark.json | tr '\n' '\0' \
    | xargs -0 git status --porcelain=v1 --untracked-files=all --
  echo "(no lines above == pass)"
  echo

  echo "=== Rule 75 surface census — sha256 + bytes per submitted file, HEAD vs BASE_SHA ==="
  python3 research/r106j/scripts/surface_census.py "$BASE_SHA"
  echo

  echo "=== the exact command frieren runs ==="
  echo "cd $REPO_ROOT && git checkout $HEAD_SHA && senpai/submit-official.sh $BASE_SHA"
} 2>&1 | tee "$OUT"

echo
echo "wrote $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
