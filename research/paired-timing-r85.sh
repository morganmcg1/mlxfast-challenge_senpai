#!/bin/bash
# Research-only (outside benchmark.json editablePaths, zero submission bytes).
#
# Matched local timing pair for R85-B Part 3: does moving 26 Metal
# kernel-source-string builders out of LagunaRuntimeModel.swift into
# LagunaKernelSources.swift cost anything on the timed path?
#
# Alternates baseline (pre-split) and candidate (post-split) arms on the same
# host in the same session so thermal drift is shared rather than confounded.
# Each arm is a full ./benchmark.sh --local-iterate, which rebuilds the scored
# worker before timing, so the split is genuinely recompiled on every switch.
#
# The baseline arm is materialized as a throwaway commit on a DETACHED HEAD, so
# the working tree stays clean for the whole run and the assignment branch ref
# is never moved. A killed run leaves the branch intact and detached HEAD is
# recovered with `git checkout --force <branch>`.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

BASE_SHA="cc5688d0dfd6347bde0efd624cd6e10fdd4cfd26"
MAIN_FILE="Sources/MLXFastModel/LagunaRuntimeModel.swift"
SPLIT_FILE="Sources/MLXFastModel/LagunaKernelSources.swift"
ROUNDS="${1:-${ROUNDS:-2}}"
OUT="${OUT:-${REPO}/../mlxfast-r85-timing}"
# Rows accumulate across invocations; the summary always re-reads every row in
# OUT so a later session tightens the estimate instead of replacing it.
SESSION="${SESSION:-$(date -u +%Y%m%dT%H%M%SZ)}"

fail() { echo "paired-timing-r85: $*" >&2; exit 1; }

[[ -z "$(git status --porcelain)" ]] || fail "worktree is dirty; commit or clean it first"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[[ "${BRANCH}" != "HEAD" ]] || fail "detached HEAD; check out the assignment branch first"
HEAD_SHA="$(git rev-parse HEAD)"
mkdir -p "${OUT}"
echo "paired-timing-r85: repo=${REPO} branch=${BRANCH} head=${HEAD_SHA} base=${BASE_SHA} rounds=${ROUNDS}"

restore_branch() { git checkout -q --force "${BRANCH}" 2>/dev/null || true; }
trap restore_branch EXIT

apply_arm() {
  case "$1" in
    baseline)
      git checkout -q --detach || fail "cannot detach HEAD"
      git checkout -q "${BASE_SHA}" -- "${MAIN_FILE}" || fail "cannot restore base ${MAIN_FILE}"
      git rm -q "${SPLIT_FILE}" || fail "cannot remove ${SPLIT_FILE}"
      git commit -q -m "TEMP r85 paired-timing baseline arm (discarded at exit)" \
        || fail "cannot commit baseline arm"
      ;;
    candidate)
      restore_branch
      [[ "$(git rev-parse HEAD)" == "${HEAD_SHA}" ]] || fail "candidate arm is not at ${HEAD_SHA}"
      ;;
    *) fail "unknown arm $1" ;;
  esac
  [[ -z "$(git status --porcelain)" ]] || fail "arm $1 left the worktree dirty"
  echo "paired-timing-r85: arm=$1 main=$(wc -c < "${MAIN_FILE}")B split_present=$([[ -f "${SPLIT_FILE}" ]] && echo yes || echo no)"
}

run_arm() {
  local arm="$1" round="$2" stem="${OUT}/${SESSION}.$1.r$2"
  apply_arm "${arm}"
  rm -f score.local-iterate.json
  echo "paired-timing-r85: === running arm=${arm} session=${SESSION} round=${round} ==="
  ./benchmark.sh --local-iterate
  local rc=$?
  git checkout -q -- Package.resolved 2>/dev/null || true
  [[ ${rc} -eq 0 ]] || fail "benchmark.sh --local-iterate failed arm=${arm} round=${round} rc=${rc}"
  [[ -f score.local-iterate.json ]] || fail "no score.local-iterate.json arm=${arm} round=${round}"
  cp score.local-iterate.json "${stem}.score.json"
  jq -c --arg arm "${arm}" --arg session "${SESSION}" --argjson round "${round}" \
    '{session:$session, arm:$arm, round:$round, decode:.metrics.decode_seconds_per_token, prefill:.metrics.prefill_seconds_per_token, passed:.metrics.passed_correctness, error:.metrics.error}' \
    "${stem}.score.json" > "${stem}.row.json"
  echo "paired-timing-r85: $(cat "${stem}.row.json")"
}

# BSD seq counts DOWN when the end is below the start, so `seq 1 0` yields
# "1 0" and would silently run two rounds. ROUNDS=0 means summary-only.
if [[ "${ROUNDS}" -ge 1 ]]; then
  for round in $(seq 1 "${ROUNDS}"); do
    for arm in baseline candidate; do
      run_arm "${arm}" "${round}"
    done
  done
fi

echo
echo "paired-timing-r85: ===== summary over every pair in ${OUT} ====="
# The paired within-round difference is the estimator: it cancels session-level
# thermal drift, which dominates the between-arm gap at this effect size.
jq -s -r '
  (group_by(.session + "|" + (.round|tostring))
   | map(select(length == 2))
   | map({
       tag: (.[0].session + " r" + (.[0].round | tostring)),
       bd:  (map(select(.arm=="baseline"))[0].decode),
       cd:  (map(select(.arm=="candidate"))[0].decode),
       bp:  (map(select(.arm=="baseline"))[0].prefill),
       cp:  (map(select(.arm=="candidate"))[0].prefill)
     })
   | map(. + {dd: (.cd - .bd), dp: (.cp - .bp)})) as $pairs |
  ([$pairs[].dd] | add / length) as $mdd |
  ([$pairs[].dp] | add / length) as $mdp |
  ([$pairs[].bd] | add / length) as $mbd |
  ([$pairs[].bp] | add / length) as $mbp |
  (($pairs | map(select(.dd > 0)) | length)) as $slower |
  "  pairs: \($pairs | length)   candidate-slower-on-decode in \($slower) of \($pairs | length)",
  ($pairs[] | "  \(.tag): decode b=\(.bd) c=\(.cd) diff=\(.dd)   prefill b=\(.bp) c=\(.cp) diff=\(.dp)"),
  "",
  "  mean paired decode diff  : \($mdd) s/token  (\($mdd / $mbd * 100) %, \($mdd * 1000000) us/step)",
  "  decode diff range        : \([$pairs[].dd] | min) .. \([$pairs[].dd] | max)",
  "  mean paired prefill diff : \($mdp) s/token  (\($mdp / $mbp * 100) %)",
  "  prefill diff range       : \([$pairs[].dp] | min) .. \([$pairs[].dp] | max)",
  "  decode_gain (mean ratio) : \($mbd / ($mbd + $mdd))   (>1 = candidate faster)",
  "  prefill_gain             : \($mbp / ($mbp + $mdp))"
' "${OUT}"/*.row.json

echo "paired-timing-r85: done branch=$(git rev-parse --abbrev-ref HEAD) head=$(git rev-parse --short HEAD)"
