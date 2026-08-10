#!/bin/bash
# Stage-3 handoff certificate: capture, on the exact current HEAD, every mechanical
# item frieren needs before spending the single remaining official draw.
# Read-only with respect to the working tree. bash 3.2 compatible.
#
# Usage: research/r106j/scripts/handoff_certificate.sh [BASE_SHA]
#
# R108-M Part 2a fix (maple-fern, 2026-08-10):
#   The old default was the hardcoded literal 446fe9875d1f95b1216628b5809a99da844e5c79.
#   That literal was already stale: the fork's origin/main is now
#   1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7. A stale BASE_SHA default is the
#   worst failure mode available here because it FAILS SILENTLY -- with a stale
#   literal, submit-official.sh preconditions 1, 7, 10, 11 and 12 all still pass,
#   and only precondition 9 (protected paths identical between origin/main and
#   BASE_SHA) catches it, at the cost of the single remaining official draw.
#   Fix: never hardcode. Derive the default from origin/main at run time, after
#   the fetch, and label which source was used. An explicit argument still wins.

set -uo pipefail

BASE_SHA_INPUT="${1:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

OUT_DIR="research/artifacts/maple-fern-r106j"
mkdir -p "$OUT_DIR"
OUT="${HANDOFF_OUT:-$OUT_DIR/handoff_certificate.txt}"

# Use the wrapper's own refspec so MAIN_SHA resolves exactly the way
# senpai/submit-official.sh:41-49 resolves it.
if ! git fetch --quiet --no-tags origin '+refs/heads/main:refs/remotes/origin/main'; then
  echo "handoff certificate: could not refresh origin/main; refusing to certify" >&2
  exit 1
fi
MAIN_SHA="$(git rev-parse --verify refs/remotes/origin/main^{commit})"
HEAD_SHA="$(git rev-parse HEAD)"

if [ -n "$BASE_SHA_INPUT" ]; then
  BASE_SHA="$BASE_SHA_INPUT"
  BASE_SHA_SOURCE="explicit argument"
else
  BASE_SHA="$MAIN_SHA"
  BASE_SHA_SOURCE="derived from origin/main at run time (no hardcoded default)"
fi

{
  echo "=== Stage-3 handoff certificate ==="
  echo "generated_utc   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "repo_root       $REPO_ROOT"
  echo "BASE_SHA        $BASE_SHA"
  echo "BASE_SHA source $BASE_SHA_SOURCE"
  echo "HEAD            $HEAD_SHA"
  echo "origin/main     $MAIN_SHA   (freshly fetched)"
  if [ "$BASE_SHA" != "$MAIN_SHA" ]; then
    echo "WARNING         BASE_SHA != origin/main. Precondition 2 below is then a"
    echo "                real test, not a tautology, and a stale BASE_SHA burns the draw."
  fi
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
  echo "cd $REPO_ROOT && git checkout $HEAD_SHA \\"
  echo "  && bash senpai/submit-official.sh $BASE_SHA --note-file <path-to-note.md>"
  echo
  echo "  * --note or --note-file is REQUIRED by 'mlxfast submit' itself; write the"
  echo "    note file BEFORE firing (mlxfast submit --help)."
  echo "  * never pass --model: the wrapper appends '--model senpai' and exits 2 if"
  echo "    you pass your own (senpai/submit-official.sh:18-23)."
  echo "  * DARKBLOOM_QMV_WIDE_CODES and DARKBLOOM_EXPERT_DOWN_BN must be UNSET"
  echo "    in the firing shell (rules 102 and 103)."
} 2>&1 | tee "$OUT"

echo
echo "wrote $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
