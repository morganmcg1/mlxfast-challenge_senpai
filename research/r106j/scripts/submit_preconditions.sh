#!/bin/bash
# Faithful, READ-ONLY rehearsal of every precondition in senpai/submit-official.sh.
#
# You cannot dry-run the wrapper: if all predicates pass it submits. So this
# script re-implements the predicates in the same order, against the same
# sources, and NEVER invokes mlxfast. It is the pass/fail table the integration
# record has to carry on the exact frozen HEAD.
#
# Every check below is transcribed from senpai/submit-official.sh at
# 2026-08-10; the line references are to that file.
#
# Usage: research/r106j/scripts/submit_preconditions.sh [BASE_SHA] [extra args to simulate...]
#
# BASE_SHA defaults to the fork's origin/main, which is what the wrapper wants
# --- NOT the advisor base and NOT the candidate commit.

set -uo pipefail

BASE_INPUT="${1:-1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7}"
shift 2>/dev/null || true
SIM_ARGS=("$@")

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT" || exit 3

OUT_DIR="research/artifacts/maple-fern-r106j"
mkdir -p "$OUT_DIR"
OUT="${PRECOND_OUT:-$OUT_DIR/submit_preconditions.txt}"

pass_n=0
fail_n=0
report() { # report <n> <name> <ok:0/1> <detail>
  local n="$1" name="$2" ok="$3" detail="$4"
  if [ "$ok" = "0" ]; then
    printf '  %-2s  PASS  %-58s  %s\n' "$n" "$name" "$detail"
    pass_n=$((pass_n + 1))
  else
    printf '  %-2s  FAIL  %-58s  %s\n' "$n" "$name" "$detail"
    fail_n=$((fail_n + 1))
  fi
}

{
echo "=== senpai/submit-official.sh precondition rehearsal (READ-ONLY) ==="
echo "generated_utc  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "repo_root      $REPO_ROOT"
echo "HEAD           $(git rev-parse HEAD)"
echo "branch         $(git rev-parse --abbrev-ref HEAD)"
echo "BASE_SHA arg   $BASE_INPUT"
echo "simulated args ${SIM_ARGS[*]:-<none>}"
echo
echo "checks:"

# --- 1. BASE_SHA is a full 40- or 64-char hex string  (wrapper :12-17)
case "$BASE_INPUT" in
  *[!0-9a-fA-F]*) ok=1; d="contains non-hex characters" ;;
  *) if [ ${#BASE_INPUT} -eq 40 ] || [ ${#BASE_INPUT} -eq 64 ]; then
       ok=0; d="len=${#BASE_INPUT}, hex"
     else ok=1; d="len=${#BASE_INPUT}, must be 40 or 64"; fi ;;
esac
report 1 "BASE_SHA is full 40/64-char hex" "$ok" "$d"

# --- 2. no --model anywhere in the trailing arguments  (wrapper :18-23)
ok=0; d="no --model in simulated args"
for a in ${SIM_ARGS[@]+"${SIM_ARGS[@]}"}; do
  case "$a" in
    --model|--model=*) ok=1; d="FOUND '$a' -> wrapper exits 2" ;;
  esac
done
report 2 "no --model passed (wrapper injects it itself)" "$ok" "$d"

# --- 3. git, jq, mlxfast all on PATH  (wrapper :24-29)
missing=""
for c in git jq mlxfast; do command -v "$c" >/dev/null 2>&1 || missing="$missing $c"; done
if [ -z "$missing" ]; then ok=0; d="git, jq, mlxfast all present"; else ok=1; d="missing:$missing"; fi
report 3 "git / jq / mlxfast on PATH" "$ok" "$d"

# --- 4. inside a git worktree  (wrapper :31-35)
if top="$(git rev-parse --show-toplevel 2>/dev/null)"; then ok=0; d="$top"; else ok=1; d="not a worktree"; fi
report 4 "run inside a git worktree" "$ok" "$d"

# --- 5. BASE_SHA resolves to a local commit  (wrapper :36-39)
if base_sha="$(git rev-parse --verify --quiet "${BASE_INPUT}^{commit}")"; then ok=0; d="$base_sha"
else ok=1; d="not a local commit"; base_sha=""; fi
report 5 "BASE_SHA resolves to a local commit" "$ok" "$d"

# --- 6. git fetch origin main succeeds  (wrapper :41-47)
#     NB: a network failure here aborts with NO submission sent, and is the only
#     condition rule 88 permits retrying.
if git fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main' >/dev/null 2>&1; then
  ok=0; d="fetched"
else ok=1; d="fetch failed (retryable: nothing was sent)"; fi
report 6 "git fetch origin main succeeds" "$ok" "$d"
main_sha="$(git rev-parse --verify refs/remotes/origin/main^{commit} 2>/dev/null || echo '')"
echo "      origin/main = ${main_sha:-<unresolved>}"

# --- 7. BASE_SHA is an ancestor of HEAD  (wrapper :49-52)
if [ -n "$base_sha" ] && git merge-base --is-ancestor "$base_sha" HEAD 2>/dev/null; then
  ok=0; d="ancestor of $(git rev-parse --short HEAD)"
else ok=1; d="NOT an ancestor of HEAD"; fi
report 7 "BASE_SHA is an ancestor of HEAD" "$ok" "$d"

# --- 8. origin/main:benchmark.json readable with usable editablePaths (wrapper :54-67)
contract="$(git show "${main_sha}:benchmark.json" 2>/dev/null)"
if [ -n "$contract" ] && jq -e '.editablePaths | type == "array" and length > 0 and all(.[]; type == "string" and length > 0)' >/dev/null <<<"$contract"; then
  n_ep="$(jq -r '.editablePaths | length' <<<"$contract")"
  ok=0; d="$n_ep editablePaths entries"
else ok=1; d="unreadable or unusable editablePaths"; n_ep=0; fi
report 8 "origin/main:benchmark.json has usable editablePaths" "$ok" "$d"

# protected_paths := benchmark.json + origin/main's editablePaths.
# NOTE: the list comes from ORIGIN/MAIN's benchmark.json, not from ours.
protected=(benchmark.json)
while IFS= read -r p; do [ -n "$p" ] && protected+=("$p"); done < <(jq -r '.editablePaths[]' <<<"$contract" 2>/dev/null)

# --- 9. protected paths byte-identical between origin/main and BASE_SHA (wrapper :73-77)
#     If BASE_SHA == origin/main this is trivially satisfied; that is exactly why
#     the wrapper wants the fork's origin/main as BASE_SHA.
if [ -n "$base_sha" ] && git diff --quiet "$main_sha" "$base_sha" -- "${protected[@]}" 2>/dev/null; then
  if [ "$main_sha" = "$base_sha" ]; then d="BASE_SHA == origin/main, trivially identical"
  else d="identical across ${#protected[@]} protected paths"; fi
  ok=0
else ok=1; d="DIFFERS -> reapply and remeasure on a current snapshot"; fi
report 9 "origin/main == BASE_SHA on all protected paths" "$ok" "$d"

# --- 10. our benchmark.json matches origin/main exactly  (wrapper :78-81)
if git diff --quiet "$main_sha" HEAD -- benchmark.json 2>/dev/null; then ok=0; d="identical"
else ok=1; d="benchmark.json differs from origin/main"; fi
report 10 "HEAD benchmark.json == origin/main benchmark.json" "$ok" "$d"

# --- 11. no skip-worktree / assume-unchanged bits under protected paths (wrapper :83-96)
bad="$(git ls-files -v -- "${protected[@]}" 2>/dev/null | awk '$1 == "S" || $1 ~ /^[a-z]$/')"
if [ -z "$bad" ]; then ok=0; d="no S/lowercase index tags"
else ok=1; d="$(printf '%s' "$bad" | wc -l | tr -d ' ') tagged entries"; fi
report 11 "no skip-worktree/assume-unchanged under protected paths" "$ok" "$d"

# --- 12. protected paths clean, INCLUDING untracked AND ignored  (wrapper :98-108)
#     This is the trap: --ignored=matching counts .DS_Store, editor swap files
#     and generated .metallib/build residue that git would otherwise hide.
status="$(git status --porcelain=v1 --untracked-files=all --ignored=matching -- "${protected[@]}" 2>/dev/null)"
if [ -z "$status" ]; then ok=0; d="clean (untracked and ignored included)"
else ok=1; d="$(printf '%s\n' "$status" | wc -l | tr -d ' ') offending entries"; fi
report 12 "protected paths clean incl. untracked AND ignored" "$ok" "$d"
if [ -n "$status" ]; then
  echo "      --- offending entries ---"
  printf '%s\n' "$status" | sed 's/^/      /'
fi

echo
echo "summary: ${pass_n} pass, ${fail_n} fail"
echo
echo "=== the exact invocation (NOT run by this script) ==="
echo "bash senpai/submit-official.sh ${BASE_INPUT} --notes \"...\""
echo "  * no --model (precondition 2)"
echo "  * DARKBLOOM_EXPERT_DOWN_BN unset (rule 103, -0.195 %)"
echo "  * DARKBLOOM_QMV_WIDE_CODES  unset (rule 102, -0.5363 %)"
echo
if [ "$fail_n" -eq 0 ]; then echo "VERDICT: all 12 predicates pass on this HEAD."
else echo "VERDICT: ${fail_n} predicate(s) FAIL on this HEAD - do not fire."; fi
} 2>&1 | tee "$OUT"

echo
echo "wrote $OUT"
exit 0
